# MC Server starter with built in backups

## Requirements

1. Docker...the rest is handled for you!

## To Run

0. Clone this repo
1. Add your google service credentials in credentials.json in the root directory (see https://developers.google.com/drive/api/quickstart/python)
2. Share the google drive folder in question with the service account
3. Rename `sample.env` to `.env` and fill in the ROOT_FOLDER and SERVER_NAME to pull from google drive
   - PROD_MC_SERVER <-- This is ROOT_FOLDER
     - backups
       - smp_server <-- This is SERVER_NAME
         - 0.zip
         - 1.zip
         - 2.zip
       - minigame_server
4. Run `docker-compose up`
   - In production mode it will automatically start
   - You can just kill the automatic python process if you are working on modifying the `start.py`
5. Enjoy
\*\* This is all very rough and WIP rn
