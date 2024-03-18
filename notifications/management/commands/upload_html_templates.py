import os
import re
from django.core.management.base import BaseCommand
from notifications.models import NotificationTemplate


class Command(BaseCommand):
    help = 'Update HTML templates for given default NotificationTemplate objects using the given HTML files or given folder containing HTML files'

    def add_arguments(self, parser):
        parser.add_argument('-folder_path', type=str, help='Path to the folder containing HTML files')
        parser.add_argument('-template_object_ids', type=list, default=[],
                            help='List of Notification template object ids')
        parser.add_argument('-html_files', type=list, default=[],
                            help='List of html template files')

    def handle(self, *args, **kwargs):
        folder_path = kwargs['folder_path']
        template_object_ids = kwargs['template_object_ids']
        html_files = kwargs['html_files']

        if folder_path and html_files:
            self.stderr.write(self.style.ERROR(f"Use either folder_path or html_files, not both"))
            return

        if folder_path and (not os.path.exists(folder_path) or not os.path.isdir(folder_path)):
            self.stderr.write(self.style.ERROR(f"Folder not found at '{folder_path}'."))
            return

        if not html_files and template_object_ids:
            for root, dirs, files in os.walk(folder_path):
                template_objects = NotificationTemplate.objects.filter(pk__in=template_object_ids)
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    with open(file_path, 'r') as file:
                        html_content = file.read()
                    if is_valid_file_name(file_name):
                        self.handle_obj_update(file_name, html_content, template_objects)

        if not template_object_ids and not html_files:
            self.stderr.write(self.style.ERROR(f"No template object ids or files provided."))
            return
        if not folder_path and template_object_ids:
            template_objects = NotificationTemplate.objects.filter(pk__in=template_object_ids)
            for html_file in html_files:
                file_content = html_file.file.read()
                if is_valid_file_name(html_file.name):
                    self.handle_obj_update(html_file.name, file_content, template_objects, decode_file=True)

        self.stdout.write(self.style.SUCCESS(
            f"HTML content updated for {NotificationTemplate.objects.count()} objects."))

    def handle_obj_update(self, file_name, file_content, template_objects, decode_file=False):
        language, name = extract_identifier_from_file_name(file_name)
        try:
            obj = template_objects.get(type=name, is_default_template=True)
            obj.set_current_language(language)
            obj.html_body = file_content if not decode_file else file_content.decode('utf-8')
            obj.save()
        except NotificationTemplate.DoesNotExist:
            self.stdout.write(self.style.NOTICE(
                f"No default NotificationTemplate object found for type '{name}'."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(
                f"An unexpected error occurred: {str(e)}"))


def extract_identifier_from_file_name(file_name: str):
    # expected format: fi-type_name_of_template.html
    lang_split = file_name.split('-')
    language = lang_split[0]
    name = lang_split[1].split('.')[0]
    return language, name


def is_valid_file_name(file_name: str) -> bool:
    pattern = r'^(fi|en|sv)-[a-zA-Z0-9_]+\.html$'
    return re.match(pattern, file_name) is not None
