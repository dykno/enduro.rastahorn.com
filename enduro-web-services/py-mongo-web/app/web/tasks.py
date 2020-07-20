from app import create_celery_app
from mongodriver import MongoDriver
import requests

#REFERENCE: https://github.com/nickjj/build-a-saas-app-with-flask/blob/master/snakeeyes/blueprints/contact/tasks.py
celery = create_celery_app()

# Standup a connection to Mongo
db_driver = MongoDriver()
db_client = db_driver.db_connection('enduro-db', 'enduro')

def is_race_name(activity_name):
    if activity_name.startswith('Sideline Cup'):
        return True
    else:
        return False

def check_segments(activity_segments):

    # Put all of our segment IDs into a list so we can compare them against
    # Segments that we actually care about.
    # Activity results will likely have a bunch of other segments that we don't
    # Care about for the race so we need to do some data reduction.
    segment_ids = []
    for segment in activity_segments:
        segment_ids.append(segment['id'])

    # Scappoose Segments
    # Seg 1: SkeetBlade - 2719392528725154538
    # Seg 2: Julie's Line - 2719392528727979754
    # Seg 3: TBD
    # Seg 4: TBD
    scappoose_segments = [2719392528725154538, 1111, 2719392528727979754]

    # Cold Creek Segments
    # Seg 1: TBD
    # Seg 2: TBD
    # Seg 3: TBD
    # Seg 4: TBD
    coldcreek_segments = [99999, 999998]

    # Post Segments
    # Seg 1: TBD
    # Seg 2: TBD
    # Seg 3: TBD
    # Seg 4: TBD
    post_segments = [11111, 111112]

    # Put all of our segment ID lists into sets so that we can do an intersection compare
    segment_ids_set = set(segment_ids)
    scappoose_segments_set = set(scappoose_segments)
    coldcreek_segments_set = set(coldcreek_segments)
    post_segments_set = set(post_segments)

    # Check if we have any common segment IDs to figure out which race we're dealing with.
    # If we find a segment ID match, then we'll call match_segments() to do the data reduction.
    if segment_ids_set.intersection(scappoose_segments_set):
        race = 'Scappoose'
        result_segments = match_segments(activity_segments, scappoose_segments)

    elif segment_ids_set.intersection(coldcreek_segments_set):
        race = 'Cold Creek'
        result_segments = match_segments(activity_segments, coldcreek_segments)

    elif segment_ids_set.intersection(post_segments_set):
        race = 'Post Canyon'
        result_segments = match_segments(activity_segments, post_segments)
    else:
        race = None
        result_segments = None

    # Return where we raced and the segment dictionaries that we care about.
    return race, result_segments

# Loop through our activity segments and compare them against race segments.
# The goal here is to drop any segments from the activity that we do not care about
# and also make sure that the segments that we do care about happened in the correct
# order. For example: we want to make sure that everybody raced Segment 1 before Segment 2
def match_segments(activity_segments, race_segments):
    result_segments = []
    segment_index = 0

    for race_segment in race_segments:
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
        # Find where we raced and which segments we care about
        race, segments = check_segments(activity['segment_efforts'])

        # If we have a race and segments that matched, then we can pull values out
        if race and segments:

            results = {
                'ath_id': athlete['id'],
                'ath_fname': athlete['firstname'],
                'ath_lname': athlete['lastname'],
                'ath_sex': athlete['sex'],
                'ath_picture': athlete['profile'],
                'race_name': race,
                'race_total_time': activity['elapsed_time'],
                'race_move_time': activity['moving_time'],
                'race_start_time': activity['start_date_local'],
                'race_elevation_gain': activity['total_elevation_gain'],
                'race_average_speed': activity['average_speed'],
                'race_max_speed': activity['max_speed']
            }

            for segment in segments:
                segment_index = segments.index(segment)
                if segment:
                    results['race_segment_%s_elapsed' % segment_index] = segment['elapsed_time']
                    results['race_segment_%s_moving' % segment_index] = segment['moving_time']
                else:
                    results['race_segment_%s_elapsed' % segment_index] = None
                    results['race_segment_%s_moving' % segment_index] = None

            print(race, segments, results)
        # If we did not match any segments or the segments are out of order then
        # do not record anything
        else:
            print('Did not find correct race segments for Racer %s -- Activity %s' % (strava_event['owner_id'], strava_event['object_id']))
    else:
        print('Did not find a valid activity name.')

    '''
    db_collection.insert({
        'object_id': strava_event['object_id']
    })
    '''

    return strava_event