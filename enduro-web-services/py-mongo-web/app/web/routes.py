from app import flask_app
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import Response
from flask import session
from functools import wraps
import json
from os import environ as env
from mongodriver import MongoDriver
import requests
from urllib.parse import urlencode

# Load Strava API config values
with open(env['STRAVA_CONFIG'], 'r') as file_in:
    strava_config = json.load(file_in)

db_driver = MongoDriver()
db_client = db_driver.db_connection('enduro-db', 'enduro')

# Handle logic to check if we are authenticated to access various resources.
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'athlete' not in session:
            return redirect('https://sideline.rastahorn.com')
        return f(*args, **kwargs)
    return decorated

@flask_app.route('/')
def index():
    if 'athlete' in session:
        return render_template('index_auth.html')
    else:
        return render_template('index.html')

@flask_app.route('/schedule')
def schedule():
    if 'athlete' in session:
        return render_template('schedule_auth.html')
    else:
        return render_template('schedule.html')

@flask_app.route('/results')
def results():
    if 'athlete' in session:
        return render_template('results_auth.html')
    else:
        return render_template('results.html')

# Handle initial User Authorization for Strava's OAuth.
# If the user grants access, we'll hit the /callback URI so we can get tokens.
@flask_app.route('/login')
def login():
    strava_authorize_dict = {
        'client_id': strava_config['client_id'],
        'response_type': 'code',
        'approval_prompt': 'auto',
        'scope': 'read,activity:read',
        'redirect_uri': 'https://sideline.rastahorn.com/callback'
    }
    strava_authorize_query = urlencode(strava_authorize_dict)
    return redirect("https://www.strava.com/oauth/authorize/?" + strava_authorize_query)

# Handle the token exchange processes (taking the initial authorization for JWTs)
# that we can store for longer periods of time.
@flask_app.route('/callback')
def callback_handling():
    auth_code = request.args.get('code')
    auth_scope = request.args.get('scope')
    #auth_state = request.args.get('state')
    auth_error = request.args.get('error')

    # Check if Strava gave us back an error. If it did then throw an error page.
    # TODO: Make this error page better.
    if auth_error is not None:
        return 'Error Retrieving Strava Information. Please try again.'

    # If we have a 'code' param and a 'scope' param then we are good to request a formal token.
    elif auth_code is not None and auth_scope is not None:
        
        payload = {
            'client_id': strava_config['client_id'],
            'client_secret': strava_config['client_secret'],
            'code': auth_code,
            'grant_type': 'authorization_code'
        }

        # Make a POST request to exchange code for tokens
        response = requests.post('https://www.strava.com/api/v3/oauth/token', params = payload)
        userinfo = response.json()

        # Set some session information to check if we're authenticated and what not.
        session['jwt_payload'] = userinfo
        session['athlete'] = userinfo['athlete']

        # Finalize our Mongo connection to store our token
        db = db_client.enduro

        # Make sure we're in the 'tokens' collection
        db_collection = db.tokens
        
        # Check if the user already has a token. This might not happen regularly but we should handle it.
        query_result = db_collection.find_one({'strava_id': userinfo['athlete']['id']})
        if query_result:
            print('User already has a token. Updating it with the latest values.')

            result_id = db_collection.update_one(
                {'_id': ObjectId(query_result['_id'])},
                {'$set':
                    {
                        'access_token': userinfo['access_token'],
                        'expires_at': userinfo['expires_at'],
                        'expires_in': userinfo['expires_in'],
                        'refresh_token': userinfo['refresh_token'],
                        'token_type': userinfo['token_type']
                    }
                }
            )

            #print(result_id)
            #print(query_result)

        # If the user doesn't have a token (e.g. this is a new user) then add it to the database.
        else:
            result_id = db_collection.insert({
                'strava_id': userinfo['athlete']['id'],
                'access_token': userinfo['access_token'],
                'expires_at': userinfo['expires_at'],
                'expires_in': userinfo['expires_in'],
                'refresh_token': userinfo['refresh_token'],
                'token_type': userinfo['token_type']
            })

            query_result = db_collection.find_one({'_id':ObjectId(result_id)})
            print('New token registered: %s' % query_result)

        return redirect('https://sideline.rastahorn.com')

    # We shouldn't hit this since we should always get an error or success back from Strava.
    # TODO: Make this error page better.
    else:
        return 'Unable to get Strava token and no error was given. Please try again.'

# Clear session data
@flask_app.route('/logout')
def logout():
    # Clear session stored data
    session.clear()
    # Redirect user to home
    return redirect('https://sideline.rastahorn.com')

# Simple authentication check. We should only hit this if we have granted access to
# a Strava account.
@flask_app.route('/dashboard')
@requires_auth
def dashboard():
    return render_template('dashboard.html',
    userinfo=session['athlete'],
    userinfo_pretty=json.dumps(session['jwt_payload'], indent=4))

# Handle inbound webhook events from Strava so we do not need to constanty poll their API.
# See: https://developers.strava.com/docs/webhooks/
@flask_app.route('/inbound_event_callback', methods=['GET', 'POST'])
def inbound_event_callback():
    
    # Check if we're handling a webhook subscription validation request
    if request.method == 'GET' and request.args.get('hub.verify_token') == strava_config['hub_verify_token']:
        if request.args.get('hub.challenge') is not None:
            hub_challenge = '{ "hub.challenge": "%s" }' % request.args.get('hub.challenge')
            return Response(hub_challenge, mimetype='application/json'), 200
        else:
            return '404!', 404

    # Check if we're handling an inbound event by first checking for a POST method and a body
    elif request.method == 'POST' and request.json is not None:
        # Then check if the POST data matches our subscription id and if we're dealing with an 'activity' update
        if request.json['subscription_id'] == strava_config['subscription_id'] and request.json['object_type'] == 'activity':
            # If we are, send the data over to a celery worker so we don't violate Strava's 2 second response time requirement
            from app.web.tasks import parse_event
            print(request.json)
            parse_event.delay(request.json)
            return 'OK', 200
        else:
            return '404!', 404
        
    # Handle anything that doesn't fit our needs.
    else:
        print('Returning 404 since our parameters are not met.')
        print(request.json)
        return '404!', 404

# Handle calls to get race results back in JSON format
# This will make it easier to expose to Javascript for client-side tables
@flask_app.route('/api/results')
def api_results():

    # Connect to the enduro DB and results collection
    db = db_client.enduro
    db_collection = db.results

    # Get all of the scappoose race results
    query_result = db_collection.find({'race_location': 'scappoose'})

    results = []

    # Loop through all the results so we can clean them up a bit
    for doc in query_result:
        empty_segment = False
        # Remove unneeded fields
        [doc.pop(key) for key in ['_id']]

        # Add a new key for the total time of each race segment combined.
        # We can't use the total_actitivy_time field because that would include transfers and climbs.
        # We will also do a quick check to make sure that all segments were completed.
        race_move_time = 0
        race_total_time = 0

        # Loop through each field in the race result
        for key in doc:

            # Check if we're dealing with a segment that does not have a time value (meaning that it wasn't completed)
            if str(key).startswith('race_segment_') and doc[key] == None:
                # Set a flag that we have an empty segment so we can record a DNF
                empty_segment = True

            # Check if we're dealing with a 'moving' time
            elif str(key).startswith('race_segment_') and str(key).endswith('moving'):
                race_move_time += doc[key]

            # Check if we're dealing with a 'total' time
            elif str(key).startswith('race_segment_') and str(key).endswith('elapsed'):
                race_total_time += doc[key]
            
            # Skip anything else
            else:
                continue
        
        if empty_segment:
            doc['race_overall_place'] = 'DNF'
            doc['race_move_time'] = 'DNF'
            doc['race_total_time'] = 'DNF'
            doc['race_time_behind'] = 'DNF'
        else:
            doc['race_move_time'] = race_move_time
            doc['race_total_time'] = race_total_time

        # Convert 'seconds' fields to minutes:seconds
        # TODO: Might not do this server side. Opting for client-side transform at the moment.
        # doc['race_total_time'] = str(timedelta(seconds=doc['race_total_time']))
        # doc['race_move_time'] = str(timedelta(seconds=doc['race_move_time']))

        results.append(doc)

    # Sort the completed times
    # Reference: https://stackoverflow.com/a/18411598
    # We need to go through this effort to make it easier to show all the results in the order that we care about
    # Which is the fastest overall moving time
    results = sorted(results, key = lambda i: float('inf') if i['race_move_time'] == 'DNF' else i['race_move_time'])

    # Assign a numerical place to each result unless it was a DNF result.
    for result in results:
        list_index = results.index(result)
        if 'race_overall_place' not in result:
            result['race_overall_place'] = list_index + 1
            if list_index == 0:
                result['race_time_behind'] = 0
            else:
                result['race_time_behind'] = result['race_move_time'] - results[0]['race_move_time']
        else:
            continue

    return jsonify(results)