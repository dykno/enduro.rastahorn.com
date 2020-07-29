from app import create_celery_app
import json
from mongodriver import MongoDriver
from os import environ as env
import requests

#REFERENCE: https://github.com/nickjj/build-a-saas-app-with-flask/blob/master/snakeeyes/blueprints/contact/tasks.py
celery = create_celery_app()

# Standup a connection to Mongo
db_driver = MongoDriver()
db_client = db_driver.db_connection('enduro-db', 'enduro')

# Load Race Segments
with open(env['RACE_CONFIG'], 'r') as file_in:
    race_config = json.load(file_in)

def is_race_name(activity_name):
    if activity_name.startswith('Sideline Cup'):
        return True
    else:
        return False

def check_race_location(activity_segments):

    # Put all of our segment IDs into a list so we can compare them against
    # Segments that we actually care about.
    # Activity results will likely have a bunch of other segments that we don't
    # Care about for the race so we need to do some data reduction.
    segment_ids = []
    for segment in activity_segments:
        segment_ids.append(segment['id'])

    race = None
    segment_ids_set = set(segment_ids)

    for key in race_config:
        race_location_set = set(race_config[key])

        if segment_ids_set.intersection(race_location_set):
            race = key
            break
    
    return race

# Loop through our activity segments and compare them against race segments.
# The goal here is to drop any segments from the activity that we do not care about
# and also make sure that the segments that we do care about happened in the correct
# order. For example: we want to make sure that everybody raced Segment 1 before Segment 2
def match_race_segments(activity_segments, race):
    result_segments = []
    segment_index = 0

    for race_segment in race_config[race]:
        print('Looking for race segment: %s' % race_segment)

        # Set a counter to see if we have looped through all the segments,
        # If we have looped through all segments and don't find a match
        # Then we'll need to handle the result as null or None.
        # This could be common if Strava doesn't register a particular segment.
        i = 0
        for activity_segment in activity_segments:
            print('Matching against: %s' % activity_segment['id'])
            if race_segment == activity_segment['id']:
                print('SUCCESS - BREAKING')

                # Next we need to check the index of our segment in the segment list.
                # Since 'race_segments' is listed in the order that the segments need
                # to occur, we can update the segment_index with each loop iteration.
                if activity_segments.index(activity_segment) >= segment_index:
                    segment_index = activity_segments.index(activity_segment)
                    result_segments.append(activity_segment)
                    i += 1
                    break
                
                # If the segments are out of order then we should not accept the submission.
                else:
                    print('Segments are out of order. Invalidating submission.')
                    result_segments = None
                    return result_segments
            else:
                i += 1
            
            # If we reach the end of activity segments, add a None.
            # This will make it easier to store and present valid result times.
            if i == len(activity_segments):
                print('Reached the end of activity segments and did not find a match. Marking segment as None')
                result_segments.append(None)

    return result_segments

# Check if the user already has an existing result populated for this race location.
def check_previous_race(db, owner_id, race_location):
    db_collection = db.results

    query_result = db_collection.find_one({'ath_id': owner_id, 'race_location': race_location})
    
    if query_result:
        print('Found previous race for Racer %s -- Location %s' % (owner_id, race_location))
        return True
    else:
        return False


@celery.task
def parse_event(strava_event):
    # Finalize our Mongo connection to store our results
    db = db_client.enduro

    # Make sure we're in the 'results' collection

    # Get the current token for user who owns the incoming request
    db_collection = db.tokens

    query_result = db_collection.find_one({'strava_id': strava_event['owner_id']})
    access_token = query_result['access_token']
    
    # Retrieve the full activity and athlete details from Strava's API
    headers = {'Authorization': 'Bearer %s' % access_token}
    activity_response = requests.get('https://www.strava.com/api/v3/activities/%s' % strava_event['object_id'], headers=headers)
    athlete_response = requests.get('https://www.strava.com/api/v3/athlete', headers=headers)

    activity = activity_response.json()
    athlete = athlete_response.json()
    
    # Check if we have a valid event name
    if is_race_name(activity['name']):

        # Find where we raced. We'll check the segments in a different function.
        # The checks are separated out to save us from processing events that are blatantly uninteresting to us
        race_location = check_race_location(activity['segment_efforts'])

        # Check if the user already has an existing result populated for this race location.
        # If they do have one, then toss this result because we only care about the first time they raced.
        previous_race = check_previous_race(db, strava_event['owner_id'], race_location)

        if race_location and not previous_race:
            
            # Find the segments that were completed
            race_segments = match_race_segments(activity['segment_efforts'], race_location)
            if race_segments:

                # If we have a race and segments that matched, then we can pull values out to store them.
                # Get the easy stuff first.
                results = {
                    'ath_id': athlete['id'],
                    'ath_fname': athlete['firstname'],
                    'ath_lname': athlete['lastname'],
                    'ath_sex': athlete['sex'],
                    'ath_picture': athlete['profile'],
                    'race_location': race_location,
                    'activity_total_time': activity['elapsed_time'],
                    'activity_move_time': activity['moving_time'],
                    'activity_start_time': activity['start_date_local'],
                    'activity_elevation_gain': activity['total_elevation_gain'],
                    'activity_average_speed': activity['average_speed'],
                    'activity_max_speed': activity['max_speed']
                }

                # Loop through the segments and store them in case some races have a different number of segments
                # We will also use this loop to calculate the total times that we care about.
                for segment in race_segments:
                    segment_index = race_segments.index(segment)
                    if segment:
                        results['race_segment_%s_elapsed' % segment_index] = segment['elapsed_time']
                        results['race_segment_%s_moving' % segment_index] = segment['moving_time']
                    else:
                        results['race_segment_%s_elapsed' % segment_index] = None
                        results['race_segment_%s_moving' % segment_index] = None

                db_collection = db.results
                
                db_collection.insert(results)

            # If we found that the segments were out of order do not record anything
            else:
                print('Did not find correct race segments for Racer %s -- Activity %s' % (strava_event['owner_id'], strava_event['object_id']))

        # If we did not find any segments that allow us to determine a location do not record anything
        else:
            print('Could not determine race location for Racer %s -- Activity %s' % (strava_event['owner_id'], strava_event['object_id']))

    # If we did not find a valid activity name do not record anything
    else:
        print('Did not find valid activity name for Racer %s -- Activity %s' % (strava_event['owner_id'], strava_event['object_id']))

    '''
    db_collection.insert({
        'object_id': strava_event['object_id']
    })
    '''

    return strava_event