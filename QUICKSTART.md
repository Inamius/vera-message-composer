# Quick Start Guide

## 1. Setup (5 minutes)

```bash
cd vera_ai

# Install dependencies
pip install -r requirements.txt

# Create .env file with your API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
nano .env
```

## 2. Generate Dataset (1 minute)

```bash
python dataset/generate_dataset.py --seed-dir dataset --out expanded
# Creates: 50 merchants, 200 customers, 100 triggers, 30 test pairs
```

## 3. Test Locally (10 minutes)

```bash
# Terminal 1: Start the API server
python main.py
# Runs on http://localhost:8000

# Terminal 2: Test composition on first 5 test pairs
python test_local.py 5
```

## 4. Validate with Judge Simulator (15 minutes)

```bash
# Edit judge_simulator.py:
# - Set LLM_PROVIDER to your provider (e.g., "anthropic")
# - Set LLM_API_KEY to your API key
# - Set BOT_URL to http://localhost:8000 (or your deployed URL)

python judge_simulator.py
# Scores your bot on all 30 test pairs
# Outputs: score breakdown by dimension
```

## 5. Deploy (varies)

### Option A: Railway (recommended for simplicity)
```bash
# Install Railway CLI
curl -fsSL https://cli.new | sh

# Login and deploy
railway link
railway up
# Get public URL from Railway dashboard
```

### Option B: Fly.io
```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Deploy
fly launch
fly deploy
# Get public URL from fly.io dashboard
```

### Option C: Docker (for any cloud)
```bash
# Create Dockerfile (example below)
docker build -t vera-bot .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-ant-... vera-bot
```

## 6. Validate Deployed Bot

```bash
# Check health
curl https://your-bot-url.fly.dev/v1/healthz

# Check metadata
curl https://your-bot-url.fly.dev/v1/metadata

# Run judge simulator against deployed URL
# Edit judge_simulator.py: BOT_URL = "https://your-bot-url.fly.dev"
python judge_simulator.py
```

## 7. Submit

1. Ensure bot is running and all 5 endpoints respond
2. Run final judge simulator check
3. Submit bot URL + this README to magicpin

---

## Key Files

| File | Purpose |
|---|---|
| `bot.py` | Core composer logic (context → message) |
| `main.py` | FastAPI server with 5 endpoints |
| `test_local.py` | Local test runner against expanded dataset |
| `ARCHITECTURE.md` | Detailed design documentation |
| `README.md` | Overview and deployment guide |
| `requirements.txt` | Python dependencies |
| `.env.example` | Environment variable template |

## Debugging

### Issue: Bot responds with generic messages
- Check: Are merchant names, offers, numbers appearing in output?
- Fix: Verify context is being loaded in /v1/context
- Debug: Run `test_local.py` with `print()` statements in bot.py

### Issue: "CTA must be binary, open_ended, or none"
- Check: Claude response has valid CTA in JSON
- Fix: Ensure prompt explicitly lists allowed CTA values
- Debug: Print raw Claude response in bot.py compose()

### Issue: Timeout on /v1/tick (>30s)
- Check: Number of triggers being processed
- Fix: Limit available_triggers in request, or optimize prompt
- Debug: Add timing prints around LLM call

### Issue: Fabrication detected by judge
- Check: Are all numbers/offers/citations from contexts?
- Fix: Review prompt — it should say "NEVER fabricate"
- Debug: Add validation layer to check message against context before returning

## Success Criteria

✅ All 5 endpoints respond correctly  
✅ /v1/context is idempotent by (context_id, version)  
✅ Messages average 40+/50 across 30 test pairs  
✅ No fabrication, no repetition, no off-voice  
✅ Multi-turn capability (bonus): handles replies intelligently  
✅ All responses complete within 30s  

---

**Built with**: Claude + FastAPI + Anthropic API  
**Challenge**: magicpin AI Challenge — Vera Message Engine  
**Status**: Ready for submission
