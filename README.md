# LightRAG RAG System

Research project for creating a Retrieval-Augmented Generation system based on LightRAG.

## Installation and Setup

1. Copy the environment variables example:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your LLM provider keys.

3. Start the services:
   ```bash
   docker compose up -d
   ```

4. Open the web interface: http://localhost:9621/webui

## Checks

```bash
make check
```

## LLM Assistants

The project is developed using Claude Code. Agent instruction files:
- `AGENTS.md` — general rules
- `CLAUDE.md` — Claude Code settings

## Structure

```
├── src/               importable code
├── tests/             tests
├── notebooks/         research analysis
├── configs/           experiment configs
├── docs/adr/          decision log
├── results/           tables and figures
├── data/              data (not committed)
├── docker-compose.yaml
├── .env.example
├── Makefile
└── README.md
```
