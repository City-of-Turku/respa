import { alertPopup, Paginate, getErrorMessage } from './utils';


let paginator;
const SELECTED_LANGUAGE = $('html').attr('lang');
const main = $("div[data-paginate=true]");

export function initializeEventHandlers() {
    paginator = new Paginate(main);
    bindResultsPerPageButtons();
    bindQualityToolLinkEditCreateButton();
    bindResourceFilter();
    bindSelectAllButton();
    bindSelectPaginatorItems();
}

function bindResultsPerPageButtons() {
    let resourceFilter = $("#resource-filter");
    let menu = $('div[id=per-page-menu]');
    let options = $(menu).find('label');
    $(options).find('input').on('click', (e) => {
        $(options).removeClass('btn-selected');
        let option = $(e.target)
        $(option).parent('label').addClass('btn-selected');
        let perPage = $(option).data('value');
        paginator.perPage = perPage;
        let filter = $(resourceFilter).val();
        filter ? paginator.filter(filter, paginator.page) : paginator.reset(paginator.page);
    });
}

let removeAllButton = $(`<a href="javascript://"
                            id="remove-all-btn"
                            class="btn btn-primary inverse small-text align-middle"
                            style="margin-top: 10px">
                            <i class='glyphicon glyphicon-remove icon-left' aria-hidden="true"></i>
                            <span></span>
                        </a>`);


function resetAllStates() {
    $(paginator.items)
        .find('input:checked')
        .each((_, val) => $(val).prop('checked', false));
}


function bindSelectPaginatorItems() { $(paginator.items).on('click', updateSelectAllButton); }

function bindResourceFilter() {
    let resourceFilter = $("#resource-filter");
    $(resourceFilter).on('input', () => {
        let search = $(resourceFilter).val();
        search ? paginator.filter(search) : paginator.reset();

        if (!paginator.current()) {
            $(main).addClass('justify-center');
            $(main).removeClass('border-thick');
        } else {
            $(main).removeClass('justify-center');
            $(main).addClass('border-thick');
        }
    });
}

function updateSelectAllButton() {
    let selectBtn = $("#select-all-btn");
    $(selectBtn).text(`${{
        'fi': 'Valitse kaikki',
        'en': 'Select all',
        'sv': 'Välj alla'
    }[SELECTED_LANGUAGE]}`);

    let resources = $(paginator.items).find('input:checked');

    if (resources.length === 0) {
        $(removeAllButton).remove();
    } else {
        $(removeAllButton)
        .on('click', () => {
            $(paginator.items)
                .find('input:checked')
                .prop('checked', false);
            resetAllStates();
            updateSelectAllButton();
        })
        .appendTo($(selectBtn).parent())
        .find('span')
        .text(`${{
            'fi': `Poista kaikki ${resources.length} valintaa`,
            'sv': `Avmarkera alla ${resources.length}`,
            'en': `Remove all ${resources.length} selected`
        }[SELECTED_LANGUAGE]}`);
    }
}

function bindSelectAllButton() {
    let selectBtn = $("#select-all-btn");
    $(selectBtn).on('click', () => {
        $(paginator.items)
            .find('input:visible:not(:checked)')
            .prop('checked', true);
        updateSelectAllButton();
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