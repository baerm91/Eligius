from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from import_export.formats.base_formats import XLSX
from .resources import ObjLSNOResource

class ExportObjLSNO(APIView):
    def get(self, request):
        dataset = ObjLSNOResource().export()
        export_format = XLSX()
        
        response = HttpResponse(dataset.export(export_format), content_type=export_format.CONTENT_TYPE)
        response['Content-Disposition'] = 'attachment; filename="exported_data.xlsx"'
        
        return response


@api_view(['POST'])
@permission_classes([AllowAny])
def obtain_auth_token(request):
    """
    API endpoint to obtain authentication token.
    
    POST /api/api-token-auth/
    {
        "username": "your_username",
        "password": "your_password"
    }
    
    Returns:
    {
        "token": "abc123...",
        "user_id": 1,
        "username": "your_username",
        "email": "user@example.com"
    }
    """
    username = request.data.get('username')
    password = request.data.get('password')
    
    if not username or not password:
        return Response({
            'error': 'Bitte Username und Password angeben',
            'detail': 'Both username and password are required'
        }, status=400)
    
    user = authenticate(username=username, password=password)
    
    if user is None:
        return Response({
            'error': 'Ungültige Anmeldedaten',
            'detail': 'Invalid username or password'
        }, status=401)
    
    # Get or create token for this user
    token, created = Token.objects.get_or_create(user=user)
    
    return Response({
        'token': token.key,
        'user_id': user.pk,
        'username': user.username,
        'email': user.email,
        'created': created  # True if token was just created, False if it already existed
    })
