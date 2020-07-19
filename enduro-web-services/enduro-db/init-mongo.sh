#!/bin/bash
# Script to initialize the MongoDB service
# in the event that the DB disappears

user=`cat $MONGO_INITDB_USERNAME`
pass=`cat $MONGO_INITDB_PASSWORD`

mongo <<EOF
use enduro
db.createCollection("results")
db.createCollection("tokens")
db.createUser(
    {
        user    : '$user',
        pwd     : '$pass',
        roles   : [
            {
                role    : "readWrite",
                db      : "enduro"
            }
        ]
    }
)
EOF
