"""InsightFace/ArcFace embedding generation. Raw image bytes are never persisted."""
import io
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
Image.MAX_IMAGE_PIXELS = 20_000_000
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

_model=None

def _recognizer():
    global _model
    if _model is None:
        # Approved model weights should be pinned, reviewed and provisioned offline in production.
        from insightface.app import FaceAnalysis
        _model=FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
        _model.prepare(ctx_id=-1, det_size=(640,640))
    return _model

def decode_image(upload):
    limit=settings.MAX_UPLOAD_MB*1024*1024
    if upload.size>limit: raise ValueError(f'Image exceeds {settings.MAX_UPLOAD_MB} MB limit.')
    try:
        raw=upload.read()
        image=Image.open(io.BytesIO(raw))
        if image.format not in ('JPEG','PNG','WEBP'): raise ValueError('Use a JPEG, PNG, or WebP image.')
        if image.width * image.height > 20_000_000: raise ValueError('Image dimensions are too large.')
        image.load()
        image=ImageOps.exif_transpose(image).convert('RGB')
        if image.width<160 or image.height<160: raise ValueError('Image is too small. Use at least 160 by 160 pixels.')
        return np.asarray(image)[:,:,::-1].copy() # BGR for InsightFace
    except (UnidentifiedImageError,OSError): raise ValueError('The uploaded file is not a valid image.')

def embed(image):
    faces=_recognizer().get(image)
    if not faces: return None,'no_face'
    if len(faces)>1: return None,'multiple_faces'
    face=faces[0]
    x1,y1,x2,y2=face.bbox
    if (x2-x1)<90 or (y2-y1)<90: return None,'face_too_small'
    if float(face.det_score)<0.75: return None,'low_quality'
    vec=np.asarray(face.normed_embedding,dtype=np.float32)
    norm=float(np.linalg.norm(vec))
    if not np.isfinite(vec).all() or norm<1e-8: return None,'bad_embedding'
    return vec/norm,'ok'

def encrypt_embedding(vector):
    if not settings.BIOMETRIC_ENCRYPTION_KEY: raise RuntimeError('Biometric encryption key is not configured.')
    return Fernet(settings.BIOMETRIC_ENCRYPTION_KEY.encode()).encrypt(np.asarray(vector,dtype=np.float32).tobytes()).decode()

def decrypt_embedding(token):
    if not settings.BIOMETRIC_ENCRYPTION_KEY: raise RuntimeError('Biometric encryption key is not configured.')
    try: raw=Fernet(settings.BIOMETRIC_ENCRYPTION_KEY.encode()).decrypt(token.encode())
    except (InvalidToken,ValueError): raise RuntimeError('Unable to decrypt biometric record; check key management.')
    return np.frombuffer(raw,dtype=np.float32)

def cosine(a,b):
    den=float(np.linalg.norm(a)*np.linalg.norm(b))
    if den<=1e-8: return 0.0
    return float(np.dot(a,b)/den)

def liveness_check(_image):
    """Fail closed until a vetted, separately validated PAD integration is deployed."""
    if not settings.PAD_ENABLED:
        return {'status':'unavailable','message':'Presentation-attack detection is not configured; identity matching is blocked.'}
    # Do not claim a pass merely because a feature flag is on. Replace with a validated PAD adapter.
    return {'status':'unavailable','message':'PAD adapter is not installed; identity matching is blocked.'}
