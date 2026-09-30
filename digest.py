name: Run Daily Geopolitical Digest

on:
  schedule:
    # Запуск щодня о 06:00 UTC (це відповідає ранку за київським часом)
    - cron: '0 6 * * *'
  workflow_dispatch: # Дозволяє запускати скрипт вручну кнопкою на GitHub у будь-який момент

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install --no-cache-dir -r requirements.txt

      - name: Run Claude Digest Script
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHANNEL_ID: ${{ secrets.TELEGRAM_CHANNEL_ID }}
        run: |
          python digest_claude.py
