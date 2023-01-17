import { Paginate, ajaxRequest } from './utils';


let paginator;
const SELECTED_LANGUAGE = $('html').attr('lang');
const main = $("div[data-paginate=true]");

export function initializeEventHandlers() {
    paginator = new Paginate(main);
    bindRestoreButton();
    bindSelectAllButton();
    bindResourceFilter();
    bindSelectPaginatorItems();
    bindResultsPerPageButtons();
}


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


function resetAllStates() {
    $(paginator.items)
        .find('input:checked')
        .each((_, val) => $(val).prop('checked', false));
}


let removeAllButton = $(`<a href="javascript://"
                            id="remove-all-btn"
                            class="btn btn-primary inverse small-text align-middle"
                            style="margin-top: 10px">
                            <i class='glyphicon glyphicon-remove icon-left' aria-hidden="true"></i>
                            <span></span>
                        </a>`);


function bindSelectPaginatorItems() { $(paginator.items).on('click', updateSelectAllButton); }

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


function bindRestoreButton() { 
    let btn = $("a[id=restore-resources-btn]");
    let csrf_token = $(btn).parent().find('input[name=csrfmiddlewaretoken]');
    $(btn).on('click', (e) => {
        e.preventDefault();
        ajaxRequest(
            'POST',
            window.location.replace('#',''),
            { 'resources': paginator.getSelectedItems('id') },
            csrf_token.val(),
            (response) => { window.location = response.redirect_url; },
            (response) => { alertPopup(getErrorMessage(response), 'error'); }
        )
    });
}
