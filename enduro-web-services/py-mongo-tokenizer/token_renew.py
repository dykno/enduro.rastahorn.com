from datetime import datetime
from bson.objectid import ObjectId
import json
from os import environ as env
from mongodriver import MongoDriver
import requests

# Load Strava API config values
with open(env['STRAVA_CONFIG'], 'r') as file_in:
    strava_config = json.load(file_in)

# Establish our mongo connection
driver = MongoDriver()
client = driver.db_connection('enduro-db', 'enduro')
db = client.enduro
collection = db.tokens

# Get a mongo cursor that has all of the tokens in the collection
# This probably wouldn't scale in the real world but we likely
# Will not have very many
all_tokens = collection.find()

# Iterate through the cursor and request new tokens from Strava.
# We could implement some logic here to see if we _actually_ need
# to refresh the token but we're not dealing with much data.
# If Strava gives us back the same token then it's not a huge deal.
for token_record in all_tokens:

    print('On token for %s' % token_record['strava_id'])

    payload = {
            'client_id': strava_config['client_id'],
            'client_secret': strava_config['client_secret'],
            'grant_type': 'refresh_token',
            'refresh_token': token_record['refresh_token']
        }
    
    # Make a POST request to get a new token.
    response = requests.post('https://www.strava.com/api/v3/oauth/token', params = payload)

    new_token = response.json()
    if 'access_token' in new_token:
        print('Updating record.')
        result_id = collection.update_one(
            {'_id': ObjectId(token_record['_id'])},
            {'$set':
                {
                    'access_token': new_token['access_token'],
                    'expires_at': new_token['expires_at'],
                    'expires_in': new_token['expires_in'],
                    'refresh_token': new_token['refresh_token'],
                    'token_type': new_token['token_type']
                }
            }
        )
        print('Record updated.')
    else:
        print('Unable to refresh token for %s' % token_record['strava_id'])