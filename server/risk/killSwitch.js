const { getState, setState } = require('../db/schema');
const logger = require('../utils/logger');

function isActive() {
  return getState('kill_switch') === 'true';
}

function activate(reason = 'Manual activation') {
  setState('kill_switch', 'true');
  setState('kill_switch_reason', reason);
  logger.warn('🚨 KILL SWITCH ACTIVATED', { reason });

  // Await the flatten so positions are actually closed before the process continues.
  const topstepx = require('../execution/topstepxClient');
  topstepx.flattenAllPositions().catch(err =>
    logger.error('Failed to flatten positions on kill switch activation', { error: err.message })
  );
}

function deactivate() {
  setState('kill_switch', 'false');
  setState('kill_switch_reason', '');
  logger.info('✅ Kill switch deactivated — trading resumed');
}

function getReason() {
  return getState('kill_switch_reason') || '';
}

/**
 * Auto-checks daily PnL against Prop Firm strict limits.
 *
 * EMERGENCY BUFFER MODE: Account at $48,400, MLL at $48,000 ($400 buffer).
 * - Daily loss limit: $150 (= one max-sized ORB losing trade)
 *   After one loss, bot stops for the day. Second day loss = MLL risk.
 * - Daily profit cap: $800 (protects 50% consistency rule. $800 is well
 *   below 50% of the $3,000 target on any single day.)
 */
function autoCheckDailyLimits(dailyPnl) {
  const maxLossUsd   = parseFloat(process.env.MAX_DAILY_LOSS_USD || '150');
  const maxProfitUsd = parseFloat(process.env.MAX_DAILY_PROFIT_USD || '800');

  if (dailyPnl <= -maxLossUsd && !isActive()) {
    activate(`Auto: Daily loss limit hit ($${dailyPnl.toFixed(2)} / -$${maxLossUsd.toFixed(2)})`);
    return true;
  }

  if (dailyPnl >= maxProfitUsd && !isActive()) {
    activate(`Auto: Daily profit cap hit ($${dailyPnl.toFixed(2)}). Stopping to protect 50% consistency rule.`);
    return true;
  }
  return false;
}

module.exports = { isActive, activate, deactivate, getReason, autoCheckDailyLimits };
