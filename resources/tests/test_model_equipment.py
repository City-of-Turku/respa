import pytest

from resources.models import Equipment, EquipmentAlias, EquipmentCategory


@pytest.mark.django_db
def test_equipment_category_and_equipment_str_use_translated_name():
    category = EquipmentCategory.objects.create(name="Category Name")
    equipment = Equipment.objects.create(name="Projector", category=category)

    category_text = str(category)
    assert "Category Name" in category_text
    assert category.id in category_text
    assert str(equipment) == "Projector"


@pytest.mark.django_db
def test_equipment_alias_str_contains_alias_and_equipment_name():
    category = EquipmentCategory.objects.create(name="Category")
    equipment = Equipment.objects.create(name="Mic", category=category)
    alias = EquipmentAlias.objects.create(name="Microphone", language="en", equipment=equipment)

    alias_text = str(alias)
    assert "Microphone" in alias_text
    assert "Mic" in alias_text
