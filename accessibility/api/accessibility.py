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
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly, )
    queryset = ServicePoint.objects.all()

    def get_serializer(self, *args, **kwargs):
        data = kwargs.get('data')
        if isinstance(data, list):
            kwargs['many'] = True
        if self.request.method == 'PATCH':
            kwargs['partial'] = True
        return super(ServicePointViewSet, self).get_serializer(*args, **kwargs)

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return ServicePointUpdateSerializer
        return ServicePointSerializer
    
    def get_serializer_context(self, **kwargs):
        context = super().get_serializer_context()
        if self.request.query_params.get('include', None):
            context['includes'] = self.request.query_params.getlist('include', [])
        return context

class ServiceRequirementCreateView(generics.ListCreateAPIView):
    serializer_class = ServiceRequirementSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly, )

    queryset = ServiceRequirement.objects.all()

    def get_serializer(self, *args, **kwargs):
        data = kwargs.get('data')
        if isinstance(data, list):
            kwargs['many'] = True
        return super().get_serializer(*args, **kwargs)
