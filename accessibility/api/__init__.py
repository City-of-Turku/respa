from .accessibility import ServicePointViewSet, ServiceRequirementCreateView
from resources.api.base import register_view


register_view(ServicePointViewSet, 'accessibility')