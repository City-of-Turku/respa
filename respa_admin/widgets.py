from django import forms
from django.utils.safestring import mark_safe

class RespaRadioSelect(forms.RadioSelect):
    template_name = 'respa_admin/forms/widgets/_radio.html'
    option_template_name = 'respa_admin/forms/widgets/_radio_option.html'


class RespaCheckboxSelect(forms.CheckboxSelectMultiple):
    template_name = 'respa_admin/forms/widgets/_checkbox_select.html'
    option_template_name = 'respa_admin/forms/widgets/_checkbox_select_option.html'


class RespaCheckboxInput(forms.CheckboxInput):
    template_name = 'respa_admin/forms/widgets/_checkbox.html'


class RespaImageSelectWidget(forms.ClearableFileInput):
    template_name = 'respa_admin/forms/_image.html'


class RespaImageSelectField(forms.ImageField):
    widget = RespaImageSelectWidget()


class RespaGenericCheckboxInput(forms.CheckboxInput):
    template_name = 'respa_admin/forms/widgets/_generic_checkbox.html'



class RespaSVGWidget(forms.MultiWidget):
    def __init__(self, attrs=None):
        super().__init__([
            forms.Textarea(),
            forms.FileInput()
        ], attrs)

    def decompress(self, value):
        if value and isinstance(value, str) and value.strip().startswith('<svg'):
            return [value, None]
        elif value and hasattr(value, 'url'):
            return ['', value]
        return ['', None]
    
    def render(self, name, value, attrs=None, renderer=None):
        value = self.decompress(value)
        text_area = self.widgets[0].render(f'{name}_0', value[0], attrs, renderer)
        file_input = self.widgets[1].render(f'{name}_1', value[1], attrs, renderer)
        if value[1] and hasattr(value[1], 'url'):
            preview = mark_safe(f'<img src={value[1].url} style="max-width: 75px; max-height: 75px;"></img><br/><br/>')
            file_input = preview + file_input
        return mark_safe(f'<div>{file_input}</div><br/><div>{text_area}</div>')


    def value_from_datadict(self, data, files, name):
        file = files.get(f'{name}_1')
        if data.get(f'{name}_1-clear') == 'on':
            file = None
        return [
            data.get(f'{name}_0', '').strip(),
            file,
        ]
