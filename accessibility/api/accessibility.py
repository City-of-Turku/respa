from rest_framework import generics, views, mixins, viewsets, permissions, renderers
from rest_framework.response import Response
from django.core.exceptions import ValidationError

from accessibility.serializers import ServicePointSerializer, ServiceRequirementSerializer, ServicePointUpdateSerializer
from accessibility.models import ServicePoint, ServiceRequirement
from uuid import uuid4

from django.shortcuts import get_object_or_404

class ServicePointViewSet(viewsets.ModelViewSet):
    """
    List or Create accessibility models.
    """
    permission_classes = (permissions.AllowAny, )
    queryset = ServicePoint.objects.all().prefetch_related('service_shortages__service_requirement')

    def get_serializer(self, *args, **kwargs):
        data = kwargs.get('data')
        if isinstance(data, list):
            kwargs['many'] = True
        return super().get_serializer(*args, **kwargs)

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'POST'):
            return ServicePointUpdateSerializer
        return ServicePointSerializer

    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

class ServiceRequirementCreateView(generics.CreateAPIView):
    serializer_class = ServiceRequirementSerializer
    permission_classes = (permissions.AllowAny, )

    def get_serializer(self, *args, **kwargs):
        data = kwargs.get('data')
        if isinstance(data, list):
            kwargs['many'] = True
        return super().get_serializer(*args, **kwargs)
