from datetime import datetime, timezone, timedelta
from bson import ObjectId
from bson.errors import InvalidId
from django.contrib.auth import authenticate
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.throttling import UserRateThrottle
from .db import db, ensure_indexes
from .auth import require_operator
from recognition.engine import decode_image, embed, encrypt_embedding, decrypt_embedding, cosine, liveness_check


def now(): return datetime.now(timezone.utc)
def serial(doc):
    if not doc: return None
    out=dict(doc); out['id']=str(out.pop('_id', ''))
    for k,v in list(out.items()):
        if isinstance(v,datetime): out[k]=v.isoformat()
    return out

def log_event(request, result, score=None, matched_id=None, liveness='not_checked', reason=None):
    ensure_indexes()
    db().verification_logs.insert_one({'created_at':now(),'result':result,'similarity':round(float(score),4) if score is not None else None,
        'matched_individual_id':str(matched_id) if matched_id else None,'liveness':liveness,
        'operator_id':str(request.user.pk) if request.user.is_authenticated else 'unknown','reason':reason})

def image_from(request):
    f=request.FILES.get('image')
    if not f: raise ValueError('An image file is required.')
    return decode_image(f)

def enrollment(image, individual, request):
    vector, state=embed(image)
    if state!='ok':
        return None, {'no_face':'No face detected — please face the camera.','multiple_faces':'More than one face detected. Position one person in the frame.','face_too_small':'Move closer to the camera.','low_quality':'Image quality is too low. Improve lighting and face the camera.'}.get(state,'Could not process the face image.')
    ensure_indexes(); d=db()
    # Possible duplicate flag is review-only: never auto-merge records.
    duplicates=[]
    for item in d.face_records.find({'status':'active'}):
        if str(item.get('individual_id'))==str(individual['_id']): continue
        if cosine(vector,decrypt_embedding(item['embedding']))>=settings.REVIEW_THRESHOLD:
            duplicates.append(str(item['individual_id']))
    d.face_records.update_many({'individual_id':str(individual['_id']),'status':'active'},{'$set':{'status':'superseded','updated_at':now()}})
    record={'individual_id':str(individual['_id']),'embedding':encrypt_embedding(vector),'model':'InsightFace buffalo_l / ArcFace','embedding_version':'arcface-512-v1','enrolled_at':now(),'status':'active'}
    d.face_records.insert_one(record)
    return {'face_record_id':str(record.get('_id','')),'duplicate_review':bool(duplicates)},None

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    username=request.data.get('username',''); password=request.data.get('password','')
    user=authenticate(request,username=username,password=password)
    if not user or not user.is_active:
        return Response({'detail':'Invalid username or password.'},status=400)
    if not (user.is_staff or user.is_superuser):
        return Response({'detail':'This account is not authorized for ICEE operator access.'},status=403)
    refresh=RefreshToken.for_user(user)
    return Response({'access':str(refresh.access_token),'refresh':str(refresh),'username':user.get_username(),'role':'administrator' if user.is_superuser else 'staff'})

@api_view(['GET','POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser,FormParser,JSONParser])
def individual_list(request):
    require_operator(request); ensure_indexes(); d=db()
    if request.method=='GET':
        q=request.query_params.get('q','').strip(); filt={}
        if q: filt={'$or':[{'full_name':{'$regex':q,'$options':'i'}},{'registration_id':{'$regex':q,'$options':'i'}}]}
        filt['status']={'$ne':'deleted'}
        return Response([serial(x) for x in d.individuals.find(filt).sort('created_at',-1).limit(500)])
    data=request.data
    name=str(data.get('full_name','')).strip(); registration_id=str(data.get('registration_id','')).strip()
    if not name or not registration_id: return Response({'detail':'Full name and unique registration ID are required.'},status=400)
    if str(data.get('consent','')).lower() not in ('true','1','yes'):
        return Response({'detail':'Informed consent must be confirmed before registration.'},status=400)
    doc={'full_name':name[:160],'registration_id':registration_id[:100],'contact':str(data.get('contact',''))[:200],
         'category':str(data.get('category','staff'))[:50],'status':'active','consent_recorded':True,
         'created_at':now(),'updated_at':now(),'created_by':str(request.user.pk)}
    try: result=d.individuals.insert_one(doc)
    except Exception as e:
        if 'duplicate key' in str(e).lower(): return Response({'detail':'That registration ID is already in use.'},status=409)
        raise
    doc['_id']=result.inserted_id
    # If an image is supplied, process it immediately, retaining only the protected embedding.
    if request.FILES.get('image'):
        try:
            image=decode_image(request.FILES['image']); info,error=enrollment(image,doc,request)
            if error:
                d.individuals.delete_one({'_id':doc['_id']})
                return Response({'detail':error},status=400)
            doc['face_enrolled']=True; doc['duplicate_review']=info['duplicate_review']
        except Exception as e:
            d.individuals.delete_one({'_id':doc['_id']})
            return Response({'detail':str(e)},status=400)
    db().audit_logs.insert_one({'created_at':now(),'actor_id':str(request.user.pk),'action':'individual.created','record_id':str(result.inserted_id)})
    return Response(serial(doc),status=201)

@api_view(['GET','PATCH','DELETE'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser,FormParser,JSONParser])
def individual_detail(request,record_id):
    require_operator(request); ensure_indexes(); d=db()
    try: oid=ObjectId(record_id)
    except InvalidId: return Response({'detail':'Record not found.'},status=404)
    item=d.individuals.find_one({'_id':oid,'status':{'$ne':'deleted'}})
    if not item: return Response({'detail':'Record not found.'},status=404)
    if request.method=='GET': return Response(serial(item))
    if request.method=='DELETE':
        if not request.user.is_superuser: return Response({'detail':'Administrator privileges are required to delete records.'},status=403)
        # Soft deletion preserves a minimal audit trail while disabling face lookup.
        d.individuals.update_one({'_id':oid},{'$set':{'status':'deleted','deleted_at':now(),'updated_at':now()}})
        d.face_records.update_many({'individual_id':str(oid)},{'$set':{'status':'deleted','updated_at':now()},'$unset':{'embedding':''}})
        d.audit_logs.insert_one({'created_at':now(),'actor_id':str(request.user.pk),'action':'individual.deleted','record_id':str(oid)})
        return Response(status=204)
    allowed={'full_name','contact','category','status'}; updates={k:request.data[k] for k in allowed if k in request.data}
    if 'full_name' in updates: updates['full_name']=str(updates['full_name']).strip()[:160]
    if 'status' in updates and updates['status'] not in ('active','inactive'): return Response({'detail':'Status must be active or inactive.'},status=400)
    updates['updated_at']=now()
    d.individuals.update_one({'_id':oid},{'$set':updates})
    d.audit_logs.insert_one({'created_at':now(),'actor_id':str(request.user.pk),'action':'individual.updated','record_id':str(oid),'fields':list(updates)})
    item.update(updates); return Response(serial(item))

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser,FormParser])
@throttle_classes([UserRateThrottle])
def face_enroll(request):
    require_operator(request); ensure_indexes(); d=db()
    if str(request.data.get('consent','')).lower() not in ('true','1','yes'):
        return Response({'detail':'Informed consent is required for biometric enrollment.'},status=400)
    try: oid=ObjectId(str(request.data.get('individual_id','')))
    except InvalidId: return Response({'detail':'A valid individual_id is required.'},status=400)
    person=d.individuals.find_one({'_id':oid,'status':'active'})
    if not person: return Response({'detail':'Active individual record not found.'},status=404)
    try:
        image=image_from(request); info,error=enrollment(image,person,request)
        if error: return Response({'detail':error},status=422)
        d.audit_logs.insert_one({'created_at':now(),'actor_id':str(request.user.pk),'action':'face.enrolled','record_id':str(oid),'duplicate_review':info['duplicate_review']})
        return Response({'status':'enrolled','duplicate_review_required':info['duplicate_review'],'message':'Embedding encrypted and stored. Any possible duplicate requires authorized review.'},status=201)
    except (ValueError,RuntimeError) as e: return Response({'detail':str(e)},status=400)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser,FormParser])
@throttle_classes([UserRateThrottle])
def face_verify(request):
    require_operator(request); ensure_indexes(); d=db()
    try: oid=ObjectId(str(request.data.get('individual_id','')))
    except InvalidId: return Response({'detail':'A valid individual_id is required.'},status=400)
    person=d.individuals.find_one({'_id':oid,'status':'active'})
    if not person: return Response({'detail':'Active individual record not found.'},status=404)
    face_record=d.face_records.find_one({'individual_id':str(oid),'status':'active'})
    if not face_record: return Response({'detail':'No active face enrollment exists for this record.'},status=404)
    try: image=image_from(request)
    except ValueError as e: return Response({'detail':str(e)},status=400)
    return compare_and_log(request, image, [(person,face_record)])

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser,FormParser])
@throttle_classes([UserRateThrottle])
def face_identify(request):
    require_operator(request); ensure_indexes(); d=db()
    try: image=image_from(request)
    except ValueError as e: return Response({'detail':str(e)},status=400)
    # Only active, consented people with active embeddings are searched; nothing is sent to browser.
    pairs=[]
    for face_record in d.face_records.find({'status':'active'}):
        try: person=d.individuals.find_one({'_id':ObjectId(face_record['individual_id']),'status':'active','consent_recorded':True})
        except (InvalidId,KeyError): person=None
        if person: pairs.append((person,face_record))
    return compare_and_log(request,image,pairs)

def compare_and_log(request,image,pairs):
    try: vector,state=embed(image)
    except Exception as e: return Response({'detail':f'Recognition service error: {e}'},status=503)
    if state!='ok':
        status='no_face' if state=='no_face' else 'manual_review'
        msg={'no_face':'No face detected — please face the camera.','multiple_faces':'Multiple faces detected. Position one face in the guide.','face_too_small':'Move closer to the camera.','low_quality':'Image quality is too low for a reliable comparison.'}.get(state,'Image could not be processed.')
        log_event(request,state,reason=msg)
        return Response({'status':status,'message':msg,'liveness':'not_checked'})
    top=None; score=-1.0
    try:
        for person,record in pairs:
            sim=cosine(vector,decrypt_embedding(record['embedding']))
            if sim>score: top=(person,record); score=sim
    except RuntimeError as e: return Response({'detail':str(e)},status=503)
    if top and score>=settings.MATCH_THRESHOLD:
        # Similarity only produces a candidate; status is always manual review, never access approval.
        liveness=liveness_check(image)
        log_event(request,'candidate_for_review',score,top[0]['_id'],liveness['status'],'Human confirmation required; PAD not validated.')
        return Response({'status':'manual_review','message':'Possible match. Manual verification required; similarity is not proof of identity.','candidate':{
            'full_name':top[0].get('full_name'),'registration_id':top[0].get('registration_id'),'category':top[0].get('category'),
            'id':str(top[0]['_id'])},'similarity':round(score,4),'liveness':liveness['status'],'liveness_message':liveness['message'],'scan_time':now().isoformat()})
    log_event(request,'no_match',score if score>=0 else None,liveness='not_checked',reason='No eligible candidate met configured threshold.')
    return Response({'status':'no_match','message':'ICEE could not identify a sufficiently close match. Do not create a record automatically.','liveness':'not_checked','scan_time':now().isoformat()})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser,FormParser])
def checkin(request):
    require_operator(request); ensure_indexes(); d=db()
    # Attendance is a distinct eligibility decision; a similarity score alone is never enough.
    if request.data.get('verified') is not True or request.data.get('eligible') is not True:
        return Response({'detail':'Confirmed identity and event eligibility must be established separately before check-in.'},status=400)
    try: oid=ObjectId(str(request.data.get('individual_id','')))
    except InvalidId: return Response({'detail':'A valid individual_id is required.'},status=400)
    person=d.individuals.find_one({'_id':oid,'status':'active'})
    if not person: return Response({'detail':'Active individual record not found.'},status=404)
    event=str(request.data.get('event_id','')).strip()
    if not event:return Response({'detail':'event_id is required.'},status=400)
    try: interval=max(0,min(int(request.data.get('duplicate_interval_minutes',15)),1440))
    except (TypeError,ValueError): return Response({'detail':'duplicate_interval_minutes must be an integer.'},status=400)
    since=now()-timedelta(minutes=interval)
    existing=d.checkins.find_one({'individual_id':str(oid),'event_id':event,'created_at':{'$gte':since}})
    if existing:return Response({'status':'duplicate_prevented','checkin':serial(existing)},status=409)
    doc={'individual_id':str(oid),'event_id':event,'created_at':now(),'verification_status':'operator_confirmed','source':str(request.data.get('source','manual_or_operator'))[:40],'created_by':str(request.user.pk),'corrections':[]}
    res=d.checkins.insert_one(doc);doc['_id']=res.inserted_id
    d.audit_logs.insert_one({'created_at':now(),'actor_id':str(request.user.pk),'action':'checkin.created','record_id':str(res.inserted_id)})
    return Response({'status':'checked_in','checkin':serial(doc)},status=201)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def attendance_report(request):
    require_operator(request); ensure_indexes(); d=db()
    start=request.query_params.get('start'); end=request.query_params.get('end'); event=request.query_params.get('event_id')
    filt={}
    try:
        if start: filt.setdefault('created_at',{})['$gte']=datetime.fromisoformat(start.replace('Z','+00:00'))
        if end: filt.setdefault('created_at',{})['$lte']=datetime.fromisoformat(end.replace('Z','+00:00'))
    except ValueError:return Response({'detail':'Use ISO 8601 dates for start and end.'},status=400)
    if event:filt['event_id']=event
    entries=[serial(x) for x in d.checkins.find(filt).sort('created_at',-1).limit(5000)]
    if request.query_params.get('format')=='csv':
        import csv
        from django.http import HttpResponse
        response=HttpResponse(content_type='text/csv')
        response['Content-Disposition']='attachment; filename=icee-attendance.csv'
        writer=csv.DictWriter(response,fieldnames=['id','individual_id','event_id','created_at','verification_status','source'])
        writer.writeheader(); writer.writerows([{k:item.get(k,'') for k in writer.fieldnames} for item in entries])
        return response
    return Response({'count':len(entries),'results':entries})
