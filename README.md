# SBA Deal Finder Cloud App

This is the cloud-deployable version of your SBA Deal Finder.

## What it does

- Provides a web dashboard with a Refresh Listings button
- Pulls public listings from NJ, NY, relocatable, Quiet Light, Website Closers, Transworld, Inbar, and other sources
- Scores deals by:
  - Cash flow
  - Asking price
  - Multiple
  - SBA estimated annual debt service
  - DSCR
  - Max supportable price
  - Pricing gap
- Exports CSV and Excel

## Deploy to Streamlit Community Cloud

1. Create a free GitHub account if you do not have one.
2. Create a new GitHub repository, for example:
   `sba-deal-finder`
3. Upload these files into the repository:
   - app.py
   - scraper.py
   - config.json
   - requirements.txt
4. Go to Streamlit Community Cloud:
   https://share.streamlit.io/
5. Click **New app**.
6. Select your GitHub repository.
7. Set the main file path to:
   `app.py`
8. Click **Deploy**.

You will get a web link. Open the link and click **Refresh Listings**.

## Updating sources later

To add more listing sites, edit `config.json` in GitHub.

Add a source like this:

```json
{
  "name": "Broker Name",
  "url": "https://example.com/listings",
  "enabled": true,
  "max_links": 50
}
```

Save the file. Streamlit will redeploy automatically.

## Limitations

Some sites hide financials behind NDAs, login pages, JavaScript, or anti-scraping tools. The app can only pull data visible in public HTML.
