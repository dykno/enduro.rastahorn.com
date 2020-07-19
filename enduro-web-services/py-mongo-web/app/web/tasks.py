from app import create_celery_app
from mongodriver import MongoDriver

#REFERENCE: https://github.com/nickjj/build-a-saas-app-with-flask/blob/master/snakeeyes/blueprints/contact/tasks.py
celery = create_celery_app()

db_driver = MongoDriver()
db_client = db_driver.db_connection('enduro-db', 'enduro')

@celery.task
def parse_event(strava_event):
    # Finalize our Mongo connection to store our token
    db = db_client.enduro

    # Make sure we're in the 'tokens' collection
    db_collection = db.results

    result_id = db_collection.insert({
        'object_id': strava_event['object_id']
    })

    return strava_event