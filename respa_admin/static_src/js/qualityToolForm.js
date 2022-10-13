import { alertPopup, Paginate, getErrorMessage } from './utils';


let paginator;
const SELECTED_LANGUAGE = $('html').attr('lang');
const main = $("div[data-paginate=true]");

export function initializeEventHandlers() {
    paginator = new Paginate(main);

    bindGenerateLinkButton(); 
}



function bindGenerateLinkButton() {
    let btn = $("button[id=link-resource-btn]");

    $(btn).on('click', (e) => {
        e.preventDefault();
        let apiUrl = `${window.location.origin}/ra/qualitytool`;
        let resources = [];
        $(paginator.items)
            .find('input:checked')
            .each((_, resource) => resources.push($(resource).attr('id')));
        
        let target = $("div[data-qualitytool-target=true]").find('input:checked');
        
        let name = {};
        
        $('[id=all-languages] data').each((_, lang) => {
            name[$(lang).prop('value')] = $(target).data(`target-name-${$(lang).prop('value')}`)
        });

        let csrf_token = $(btn).parent().find('input[name=csrfmiddlewaretoken]');

        $.ajax({
            type: 'POST',
            url: `${apiUrl}/create/`,
            dataType: 'json',
            contentType: 'application/json',
            beforeSend: (xhr) => {
                xhr.setRequestHeader("X-CSRFToken", csrf_token.val())
            },
            data: JSON.stringify({
                'resources': resources,
                'target_id': target.data('value'),
                'name': name
            }),
            success: (response) => {
                alertPopup(response.message);
            },
            error: (response) => {
                alertPopup(getErrorMessage(response), 'error');
            }
        });
    });

    setInterval(() => {
        if ($(paginator.items).find('input:checked').length > 0 
            && $("div[data-qualitytool-target=true]").find('input:checked').length > 0) {
            $(btn).prop('disabled', false);
        } else {
            $(btn).prop('disabled', true);
        }
    }, 200);
}