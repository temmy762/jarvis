<<<<<<< HEAD
# jarvis
An AI personal assistant
=======
# Jarvis AI Agent (Python)

Jarvis is a fully autonomous AI agent with persistent memory, tool execution, and multi-modal interaction (Telegram text/voice, email, calendar, and more). This repository contains the Python backend built with FastAPI and designed for deployment on a VPS.

## Features (Planned)

- Persistent memory via Supabase
- Short-term context and reasoning via OpenAI models
- Telegram integration (text and voice)
- Gmail and calendar tools
- Voice in/out via Whisper and TTS
- Clean, modular architecture for easy extension

## Installation

1. Clone the repository to your VPS or local machine.
2. Create and activate a Python 3.10+ virtual environment.
3. Install dependencies:

   pip install -r requirements.txt

4. Copy `.env.example` to `.env` and fill in your credentials:

   - OPENAI_API_KEY
   - SUPABASE_URL
   - TELEGRAM_BOT_TOKEN
   - SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY)

## Running the Server

Start the FastAPI application using Uvicorn:

   uvicorn main:app --host 0.0.0.0 --port 8000

This will expose the `/health` endpoint for basic health checks and a placeholder `/webhook/telegram` endpoint to be implemented in later phases.
>>>>>>> c457798 (git add .)
