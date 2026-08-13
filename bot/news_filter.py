import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
import logging
import os
import json

logger = logging.getLogger(__name__)

class NewsFilter:
    def __init__(self):
        self.url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.high_impact_events = [] # list of dicts: {'time': datetime, 'title': str}
        self.last_fetch = None
        self.cache_file = "news_cache.json"
        
    def fetch_events(self):
        """Fetches the ForexFactory XML and parses USD High Impact events."""
        eastern = pytz.timezone('US/Eastern')
        
        # Check local cache first to prevent 429 rate limits on process restarts
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    cache_data = json.load(f)
                cache_time = datetime.fromisoformat(cache_data["last_fetch"])
                if (datetime.now(eastern) - cache_time).total_seconds() < 86400:
                    events = []
                    for e in cache_data["events"]:
                        events.append({
                            "time": datetime.fromisoformat(e["time"]),
                            "title": e["title"]
                        })
                    self.high_impact_events = events
                    self.last_fetch = cache_time
                    logger.info(f"Loaded {len(self.high_impact_events)} High Impact USD events from local cache.")
                    return
            except Exception as e:
                logger.error(f"Error reading news cache: {e}")

        try:
            resp = requests.get(self.url, headers=self.headers, timeout=10)
            if resp.status_code != 200:
                logger.error(f"Failed to fetch economic calendar, status: {resp.status_code}")
                # Set last_fetch to 23 hours and 50 minutes ago so we back off for 10 minutes instead of 24h
                self.last_fetch = datetime.now(eastern) - timedelta(hours=23, minutes=50)
                return
                
            root = ET.fromstring(resp.content)
            events = []
            
            for event in root.findall("event"):
                if event.find("country").text == "USD" and event.find("impact").text == "High":
                    date_str = event.find("date").text
                    time_str = event.find("time").text
                    title = event.find("title").text
                    
                    if not time_str or time_str == "All Day":
                        continue
                        
                    # The XML feed returns times in UTC
                    dt_str = f"{date_str} {time_str}"
                    try:
                        # Example: 07-29-2026 6:00pm
                        dt_obj = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                        dt_aware = pytz.utc.localize(dt_obj).astimezone(eastern)
                        events.append({"time": dt_aware, "title": title})
                    except Exception as e:
                        logger.error(f"Error parsing date/time for event {title}: {e}")
            
            self.high_impact_events = events
            self.last_fetch = datetime.now(eastern)
            
            # Save to local cache
            try:
                cache_data = {
                    "last_fetch": self.last_fetch.isoformat(),
                    "events": [{"time": e["time"].isoformat(), "title": e["title"]} for e in events]
                }
                with open(self.cache_file, "w") as f:
                    json.dump(cache_data, f)
            except Exception as e:
                logger.error(f"Error saving news cache: {e}")
                
            logger.info(f"Loaded {len(self.high_impact_events)} High Impact USD events from API.")
            
        except Exception as e:
            logger.error(f"Error fetching ForexFactory API: {e}")
            self.last_fetch = datetime.now(eastern) - timedelta(hours=23, minutes=50)

    def is_news_blackout(self, current_time_est):
        """
        Returns True if current_time_est is within 10 minutes before 
        or 15 minutes after a high-impact news event.
        """
        # Refresh events once a day
        if self.last_fetch is None or (current_time_est - self.last_fetch).total_seconds() > 86400:
            self.fetch_events()
            
        for event in self.high_impact_events:
            event_time = event["time"]
            start_blackout = event_time - timedelta(minutes=10)
            end_blackout = event_time + timedelta(minutes=15)
            
            if start_blackout <= current_time_est <= end_blackout:
                return True, event["title"]
                
        return False, ""
