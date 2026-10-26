from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import PermissionDenied

class OperatorTokenAuthentication(TokenAuthentication):
    keyword='Token'

def require_operator(request):
    user=request.user
    if not user or not user.is_authenticated or not (user.is_staff or user.is_superuser):
        raise PermissionDenied('An authorized operator account is required.')
