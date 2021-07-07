from decimal import Decimal
import pytest

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from payments.models import Product


@pytest.mark.django_db
@pytest.fixture
def user_with_permissions():
    user = get_user_model().objects.create(
        username='test_permission_user',
        first_name='Test',
        last_name='Tester',
        email='test@tester.com',
        preferred_language='en'
    )

    content_type = ContentType.objects.get_for_model(Product)
    perm_view = Permission.objects.get(codename='view_product', content_type=content_type)
    perm_add = Permission.objects.get(codename='add_product', content_type=content_type)
    perm_change = Permission.objects.get(codename='change_product', content_type=content_type)
    perm_del = Permission.objects.get(codename='delete_product', content_type=content_type)
    user.user_permissions.add(perm_view, perm_add, perm_change, perm_del)
    user.save()
    return user


@pytest.fixture()
def product_api(resource_in_unit):
    product = Product.objects.create(
        name_fi='Kahvipullat',
        name_en='Coffee and buns',
        sku='coffee-buns-1',
        price=Decimal('3.50')
    )
    product.resources.set([resource_in_unit])
    return product


@pytest.fixture
def list_url():
    return reverse('product-list')


@pytest.mark.django_db
@pytest.fixture
def detail_url(product_api):
    product_api.save()
    return reverse('product-detail', kwargs={'pk': product_api.pk})


@pytest.mark.django_db
@pytest.fixture
def product_data():
    return {
        "sku": "soft-drinks-1",
        "name": {
            "fi": "Limpparit",
            "en": "Soft drinks"
        },
        "price": "7.30"
    }


@pytest.mark.django_db
def test_product_view_without_model_permissions(api_client, user, list_url):
    """
    Tests that a user without permissions cannot view a product.
    """
    response = api_client.get(list_url)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.get(list_url)
    assert response.status_code == 403


@pytest.mark.django_db
def test_product_view_with_model_permissions(api_client, user_with_permissions, list_url):
    """
    Tests that a user with permissions can view a product.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.get(list_url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_product_create_without_model_permissions(api_client, user, list_url, product_data):
    """
    Tests that a user without permissions cannot create a product.
    """
    response = api_client.post(list_url, data=product_data)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.post(list_url, data=product_data)
    assert response.status_code == 403


@pytest.mark.django_db
def test_product_create_with_model_permissions(api_client, user_with_permissions, list_url, product_data):
    """
    Tests that a user with permissions can create a product.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.post(list_url, data=product_data)
    assert response.status_code == 201


@pytest.mark.django_db
def test_product_update_without_model_permissions(api_client, user, detail_url, product_data):
    """
    Tests that a user without permissions cannot update a product.
    """
    response = api_client.put(detail_url, data=product_data)
    assert response.status_code == 401

    api_client.force_authenticate(user=user)
    response = api_client.put(detail_url, data=product_data)
    assert response.status_code == 403


@pytest.mark.django_db
def test_product_update_with_model_permissions(api_client, user_with_permissions, detail_url, product_data):
    """
    Tests that a user with permissions can update a product.
    """
    api_client.force_authenticate(user=user_with_permissions)
    response = api_client.put(detail_url, data=product_data)
    assert response.status_code == 200