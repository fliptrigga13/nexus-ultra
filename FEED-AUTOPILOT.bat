
@echo off
title NEXUS SWARM: INTELLIGENCE FEED AUTOPILOT
echo [!] Starting Sensory Feed Sequence...

echo 1/3: Ingesting Intelligence Manifesto...
python "c:\Users\fyou1\Desktop\New folder\nexus-ultra\INGEST_MANIFESTO.py"
echo ------------------------------------------

echo 2/3: Gathering Internal Sentience (Logs, Files, Feedback)...
python "c:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_sentience_feed.py"
echo ------------------------------------------

echo 3/3: Fetching Market Trends (AI Security News)...
python "c:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_market_feed.py"
echo ------------------------------------------

echo [SUCCESS] Your Swarm has been fed. They are now processing the new context in the Blackboard.
pause
