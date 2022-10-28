import { alertPopup, Paginate, getErrorMessage } from './utils';


let paginator;
const SELECTED_LANGUAGE = $('html').attr('lang');
const main = $("div[data-paginate=true]");

export function initializeEventHandlers() {
    paginator = new Paginate(main);
    bindResultsPerPageButtons();
    bindQualityToolLinkEditCreateButton();
}

function bindResultsPerPageButtons() {
    let menu = $('div[id=per-page-menu]');
    let options = $(menu).find('label');
    $(options).find('input').on('click', (e) => {
        $(options).removeClass('btn-selected');
        let option = $(e.target)
        $(option).parent('label').addClass('btn-selected');
        let perPage = $(option).data('value');
        paginator.perPage = perPage;
        paginator.reset(paginator.page);
    });
}

function ajaxRequest(type, url, data, csrfmiddlewaretoken) {
    $.ajax({
        type: type,
        url: url,
        dataType: 'json',
        contentType: 'application/json',
        beforeSend: (xhr) => {
            xhr.setRequestHeader('X-CSRFToken', csrfmiddlewaretoken)
        },
        data: JSON.stringify(data),
        success: (response) => {
            window.location = response.redirect_url;
        },
        error: (response) => {
            alertPopup(getErrorMessage(response), 'error');
        }
    })
}

function getSelectedResources() {
    let resources = [];
    $(paginator.items)
        .find('input:checked')
        .each((_, resource) => resources.push($(resource).attr('id')));
    return resources;
}

function getTargetNames(target) {
    let name = {};
    $('[id=all-languages] data').each((_, lang) => {
        name[$(lang).prop('value')] = $(target).data(`target-name-${$(lang).prop('value')}`)
    });
    return name;
}

function bindQualityToolLinkEditCreateButton() {
    let btn = $("a[id=qualitytool-link-btn]");
    $(btn).on('click', (e) => {
        e.preventDefault();
        let target = $("div[data-qualitytool-target=true]").find('input:checked');
        let name = getTargetNames(target);
        let csrf_token = $(btn).parent().find('input[name=csrfmiddlewaretoken]');

        ajaxRequest(
            'POST', 
            `${window.location}`.replace('#',''),
            {
                'resources': getSelectedResources(),
                'target_id': target.data('value'),
                'name': name
            },
            csrf_token.val()
        )
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