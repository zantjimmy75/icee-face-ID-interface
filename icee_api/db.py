from functools import lru_cache
from pymongo import MongoClient, ASCENDING, DESCENDING
from django.conf import settings

@lru_cache(maxsize=1)
def client():
    return MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=4000, connectTimeoutMS=4000)

def db():
    return client()[settings.MONGO_DATABASE]

def ensure_indexes():
    d=db()
    d.individuals.create_index('registration_id', unique=True)
    d.individuals.create_index([('status',ASCENDING),('category',ASCENDING)])
    d.face_records.create_index([('individual_id',ASCENDING),('status',ASCENDING)])
    d.verification_logs.create_index([('created_at',DESCENDING)])
    d.checkins.create_index([('individual_id',ASCENDING),('event_id',ASCENDING),('created_at',DESCENDING)])
