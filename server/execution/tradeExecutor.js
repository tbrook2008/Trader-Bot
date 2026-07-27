/**
 * server/execution/tradeExecutor.js
 * Full trade execution pipeline
 */
require('dotenv').config();
const alpaca        = require('./alpacaClient');
const topstepx      = require('./topstepxClient');
const validator     = require('../risk/validator');
const { logTrade }  = require('../db/tradeLogger');
const memory        = require('../db/strategyMemory');
const { setState, getDb }  = require('../db/schema');
const logger        = require('../utils/logger');
const fs = require('fs');
const path = require('path');
const { sendSMS } = require('../utils/notifier');

let symbolParamsCache = null;
function getSymbolParams(symbol) {
  if (global.OPTIMIZE_PARAMS) return global.OPTIMIZE_PARAMS;
  if (!symbolParamsCache) {
    try {
      const p = path.join(__dirname, '../data/symbolParams.json');
      if (fs.existsSync(p)) symbolParamsCache = JSON.parse(fs.readFileSync(p, 'utf-8'));
      else symbolParamsCache = {};
    } catch (e) { symbolParamsCache = {}; }
  }
  return symbolParamsCache[symbol] || {};
}

const orbStrategy    = require('../quantitative/orbStrategy');
const propRiskManager = require('../risk/propRiskManager');
const { calculateATR, getDynamicATRMultiplier } = require('../quantitative/atr');
const { analyzeVolume, classifyVolume } = require('../quantitative/volumeProfile');

const DRY_RUN            = process.env.DRY_RUN === 'true';
const ATR_MULTIPLIER     = parseFloat(process.env.ATR_MULTIPLIER        || '3.5');

function getGlobexSessionDate() {
  const now = new Date();
  const etNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  // After 5 PM ET, it's the NEXT Globex session date
  if (etNow.getHours() >= 17) {
    etNow.setDate(etNow.getDate() + 1);
  }
  const yyyy = etNow.getFullYear();
  const mm = String(etNow.getMonth() + 1).padStart(2, '0');
  const dd = String(etNow.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

/**
 * Full trade execution pipeline based purely on math.
 * @param {{ bundle }} params
 */
async function execute({ bundle }) {
  const symbol = bundle.symbol;
  const price  = bundle.price;
  const mode   = process.env.TRADING_MODE || 'paper';
  const history = bundle.history;
  const history5m = bundle.history5m;

  const params = getSymbolParams(symbol);
  if (Object.keys(params).length === 0) {
    logger.warn('Trade rejected: Symbol has no optimized parameters', { symbol });
    return { executed: false, reason: 'Symbol not optimized or profitable in symbolParams.json' };
  }

  // ── Opening Range Breakout (ORB) Signal ──────────────────────────────────────
  // ORB builds the 9:30–10:00 AM ET range from 1-min bars, then fires on the
  // first clean breakout. One trade per symbol per day, stop = opposite range side.
  const signal = orbStrategy.evaluate(history, symbol);
  if (!signal) {
    return { executed: false, reason: 'ORB: no signal (range building, no breakout, or already traded today)' };
  }

  // ── Safety gate: opening range must be TIGHT enough to fit within MLL buffer ──
  // With only ~$400 MLL buffer, a wide stop risks blowing the account in one trade.
  // Max range: MGC=5pts ($50/contract), MNQ=35pts ($70/contract at 1 contract)
  const MAX_RANGE = { MGC: 5, MNQ: 35, MES: 4, GC: 5, NQ: 35 };
  const rangeWidth = parseFloat(signal.rangeWidth);
  const maxAllowedRange = MAX_RANGE[symbol];
  if (maxAllowedRange && rangeWidth > maxAllowedRange) {
    logger.warn('ORB blocked: opening range too wide for MLL buffer', {
      symbol, rangeWidth: rangeWidth.toFixed(2), maxAllowed: maxAllowedRange
    });
    return { executed: false, reason: `ORB: range ${rangeWidth.toFixed(2)} > max ${maxAllowedRange} — stop too wide for MLL buffer` };
  }

  // ── Session time filter ───────────────────────────────────────────────────────
  const currentCandle = history[history.length - 1];
  let cTime = currentCandle.timestamp || currentCandle.time;
  if (typeof cTime === 'string') cTime = new Date(cTime).getTime();
  else if (typeof cTime === 'number' && cTime < 10000000000) cTime *= 1000;

  const now = new Date(cTime || Date.now());
  const nyTimeStr = now.toLocaleString('en-US', { timeZone: 'America/New_York' });
  const nyTime = new Date(nyTimeStr);
  if (nyTime.getHours() === 16) {
    return { executed: false, reason: 'Market Closed (16:00 - 17:00 ET)' };
  }

  const direction = signal.action;
  const strategy  = signal.strategy  || 'ORB';
  const regime    = signal.regime    || 'opening_range';

  logger.info('ORB signal generated', {
    symbol, direction, regime,
    rangeHigh: signal.rangeHigh?.toFixed(2),
    rangeLow:  signal.rangeLow?.toFixed(2),
    rangeWidth: rangeWidth.toFixed(2),
    entry:  signal.entry?.toFixed(2),
    stop:   signal.stopLoss?.toFixed(2),
    target: signal.target?.toFixed(2),
  });
  
  const volClass = classifyVolume(history).toUpperCase();

  // ORB is inherently directional (breaks above = LONG, breaks below = SHORT).
  // No additional macro trend filter needed — the range itself is the filter.

  logger.info('Trade executor started', {
    symbol,
    direction,
    regime,
    strategy
  });

  let account = { balance: 50000, canTrade: true };
  if (!DRY_RUN) {
    try {
      account = await topstepx.getAccountBalance() || account;
      if (!account) throw new Error('TopstepX returned null account balance');
    } catch (err) {
      logger.error('Failed to fetch TopstepX account data', { error: err.message });
      return { executed: false, reason: 'TopstepX account fetch failed' };
    }
  }

  const liveBalance = account.currentBalance || account.accountBalance || account.balance || 50000;

  if (!account.canTrade && !DRY_RUN) {
    logger.warn('Account trading is blocked — skipping', { symbol });
    return { executed: false, reason: 'TopstepX account trading blocked' };
  }

  // Step 3: Prop Firm sizing
  let qty = 0;
  try {
    qty = propRiskManager.calculatePositionSize(symbol, price, signal.stopLoss);
  } catch (err) {
    logger.warn('Failed to calculate position size', { symbol, error: err.message });
    return { executed: false, reason: 'Invalid position sizing' };
  }
  
  const sizing = {
    qty: qty,
    positionDollars: propRiskManager.RISK_PER_TRADE || 200
  };

  if (sizing.qty === 0) {
    logger.warn('Calculated quantity is 0, skipping trade', { symbol });
    return { executed: false, reason: 'Quantity evaluated to 0' };
  }
  
  let openTrades = [];
  try {
    const db = getDb();
    openTrades = db.prepare("SELECT * FROM trades WHERE status = 'open'").all();

    // ORB: max 2 trades per day (1 per symbol). ORB itself enforces tradedToday
    // but this DB-backed check survives server restarts.
    const today = getGlobexSessionDate();
    const todayTradesCount = db.prepare("SELECT COUNT(*) as count FROM trades WHERE timestamp LIKE ?").get(today + '%').count;
    if (todayTradesCount >= 2) {
      logger.warn('Trade blocked: Max ORB trades per day (2) reached', { todayTradesCount });
      return { executed: false, reason: 'Max 2 ORB trades per day reached' };
    }
  } catch (err) {
    logger.warn('Failed to fetch trades from DB', { error: err.message });
  }

  // Step 4: Validation (Skip Alpaca validation for now, or adapt it)
  const validation = await validator.runChecks({
    consensus: { approved: true, direction, regime }, // Mock consensus for validator backward compatibility
    symbol,
    positionDollars: sizing.positionDollars,
    alpacaAccount:   { portfolioValue: liveBalance, buyingPower: liveBalance, cash: liveBalance, equity: liveBalance, tradingBlocked: false },
    openPositions:   openTrades, // Trust DB for open positions
    liveBalance,
  });

  if (!validation.passed) {
    logger.warn('Trade blocked by validator', { symbol, failed: validation.failed });
    return { executed: false, reason: `Validator: ${validation.failed.join(', ')}` };
  }

  // Step 5: Stops & Targets mapping
  const side = direction === 'LONG' ? 'buy' : 'sell';
  const targetDist = Math.abs(price - signal.target);
  const trailPrice = Math.abs(price - signal.stopLoss);

  // Step 5b: Volume Profile check
  const volAnalysis = analyzeVolume(bundle.history, direction, symbol);
  logger.info('Volume profile', { symbol, volume: volClass, ratio: volAnalysis.ratio?.toFixed(2), reason: volAnalysis.reason });
  if (!volAnalysis.supported) {
    logger.warn('Trade blocked by volume profile', { symbol, reason: volAnalysis.reason, ratio: volAnalysis.ratio });
    return { executed: false, reason: `Volume: ${volAnalysis.reason}` };
  }

  // Step 6: Calculate Stops & Targets

  const atrStop   = signal.stopLoss;
  const atrTarget = signal.target;

  if (DRY_RUN) {
    logger.info('🔍 DRY RUN — no order submitted', {
      symbol, side, qty: sizing.qty, trailPrice: trailPrice.toFixed(2),
    });
    return { executed: false, dryRun: true, sizing, validation, reason: 'Dry run mode' };
  }

  // Step 7: Execute via TopstepX
  let order;
  const tsSymbol = symbol;

  function calculateTicks(sym, pointDistance) {
    let tickSize = 1;
    switch (sym) {
      case 'MES': tickSize = 0.25; break;
      case 'MNQ': tickSize = 0.25; break;
      case 'MYM': tickSize = 1.00; break;
      case 'M2K': tickSize = 0.10; break;
      case 'MGC': tickSize = 0.10; break;
      case 'MCL': tickSize = 0.01; break;
      case 'ES': tickSize = 0.25; break;
      case 'NQ': tickSize = 0.25; break;
      case 'CL': tickSize = 0.01; break;
      case 'GC': tickSize = 0.10; break;
      default: tickSize = 0.25; break;
    }
    return Math.round(pointDistance / tickSize);
  }

  const tpTicks = calculateTicks(symbol, targetDist);
  const slTicks = calculateTicks(symbol, trailPrice);

  try {
    const tsResponse = await topstepx.placeMarketOrder(tsSymbol, side, sizing.qty, tpTicks, slTicks, price);
    if (!tsResponse) throw new Error('TopstepX Order Failed');
    
    order = { orderId: tsResponse.orderId || 'ts-order-' + Date.now() };
    logger.info(`✅ Market order submitted to TopstepX: ${tsSymbol} | OrderID: ${order.orderId} | Qty: ${sizing.qty}`);
    sendSMS(`🚀 AI Trader ENTRY: ${direction} ${sizing.qty}x ${symbol} @ $${price}\nStop: $${atrStop.toFixed(2)}\nTarget: $${atrTarget.toFixed(2)}`);
  } catch (err) {
    const errorDetails = err.response ? err.response.data : err.message;
    logger.error('❌ Order submission failed', { symbol: tsSymbol, error: err.message, details: errorDetails });
    return { executed: false, reason: `TopstepX Error: ${err.message}` };
  }

  // Step 8: Log trade — store ATR-derived stop/target so riskMonitor can pick them up
  const tradeId = logTrade({
    symbol,
    direction,
    qty:            sizing.qty,
    entryPrice:     price,
    stopLoss:       parseFloat(atrStop.toFixed(4)),
    targetPrice:    parseFloat(atrTarget.toFixed(4)),
    alpacaOrderId:  order.orderId,
    decisionId:     strategy, // Use strategy name as decision ID for logging
    mode,
  });

  // Step 9: Strategy memory
  memory.saveSetup({
    tradeId,
    symbol,
    regime,
    direction,
    compositeScore: 80,
  });

  setState(`last_trade_${symbol}`, new Date().toISOString());

  // Topstep Prop Firm Bot: Webhook removed to decouple from the Friends Exec Node

  return {
    executed:        true,
    tradeId,
    orderId:         order.orderId,
    symbol,
    direction,
    qty:             sizing.qty,
    entryPrice:      price,
    trailPrice:      parseFloat(trailPrice.toFixed(2)),
    targetDist:      parseFloat(targetDist.toFixed(2)),
    targetPrice:     parseFloat(atrTarget.toFixed(4)),
    stopLossPrice:   parseFloat(atrStop.toFixed(4)),
    positionDollars: sizing.positionDollars,
  };
}

module.exports = { execute };
