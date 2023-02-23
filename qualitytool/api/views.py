from rest_framework import views, permissions, response
from qualitytool.manager import qt_manager
from qualitytool.api.serializers import QualityToolFeedbackSerializer, QualityToolCheckSerializer
from qualitytool.api.permissions import QualitytoolPermission

class QualityToolFormView(views.APIView):
    permission_classes = (permissions.IsAuthenticatedOrReadOnly, )
    def get(self, request, **kwargs):
        return response.Response(qt_manager.get_form())

class QualityToolTargetListView(views.APIView):
    permission_classes = (QualitytoolPermission, )
    def get(self, request, **kwargs):
        data = qt_manager.get_target_list()
        return response.Response({
            'count': len(data),
            'results': data
        })


class QualityToolFeedbackView(views.APIView):
    permission_classes = (permissions.IsAuthenticated, )
    def post(self, request, **kwargs):
        serializer = QualityToolFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        resource_quality_tool = data['resource_quality_tool']

        payload = {
            'targetId': str(resource_quality_tool.target_id),
            'rating': data['rating']
        }

        if data.get('text', None):
            payload['text'] = data['text']


        return response.Response(qt_manager.post_rating(payload))



class QualityToolCheckResourceView(views.APIView):
    permission_classes = (permissions.AllowAny, )
    def post(self, request, **kwargs):
        serializer = QualityToolCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resource = serializer.validated_data['resource']
        return response.Response({ 'has_qualitytool': resource.qualitytool.exists() })



