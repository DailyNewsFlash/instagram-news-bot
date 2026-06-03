name: Instagram News Bot

on:
  schedule:
    - cron: '0 4 * * *'    # 9:30 AM IST  — single post
    - cron: '0 7 * * *'    # 12:30 PM IST — carousel post
    - cron: '0 10 * * *'   # 3:30 PM IST  — single post
    - cron: '0 13 * * *'   # 6:30 PM IST  — carousel post
    - cron: '0 16 * * *'   # 9:30 PM IST  — single post
  workflow_dispatch:
    inputs:
      post_type:
        description: 'Post type (single or carousel)'
        required: true
        default: 'single'
        type: choice
        options:
          - single
          - carousel

jobs:
  post:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests pillow

      - name: Decide post type
        id: decide
        run: |
          if [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            echo "POST_TYPE=${{ github.event.inputs.post_type }}" >> $GITHUB_ENV
          elif [ "${{ github.event.schedule }}" = "0 7 * * *" ] || [ "${{ github.event.schedule }}" = "0 13 * * *" ]; then
            echo "POST_TYPE=carousel" >> $GITHUB_ENV
          else
            echo "POST_TYPE=single" >> $GITHUB_ENV
          fi

      - name: Run bot
        env:
          GNEWS_API_KEY: ${{ secrets.GNEWS_API_KEY }}
          UNSPLASH_ACCESS_KEY: ${{ secrets.UNSPLASH_ACCESS_KEY }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          FB_PAGE_ID: ${{ secrets.FB_PAGE_ID }}
          FB_ACCESS_TOKEN: ${{ secrets.FB_ACCESS_TOKEN }}
          IG_ACCOUNT_ID: ${{ secrets.IG_ACCOUNT_ID }}
        run: python bot.py
