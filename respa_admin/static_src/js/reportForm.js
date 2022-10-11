import { alertPopup, Paginate } from './utils';



let paginator;
const SELECTED_LANGUAGE = $('html').attr('lang');
const main = $("div[data-paginate=true]");

export function initializeEventHandlers() {
    paginator = new Paginate(main);
    setDefaultDate();

    bindSelectAllButton();
    bindGenerateButton();
    bindResourceFilter();
    bindSelectPaginatorItems();
    bindResultsPerPageButtons();

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


function setDefaultDate() {
    let date = new Date();
    $("#end-date").attr('value', date.toISOString().substr(0, 10));
    date.setMonth(date.getMonth() - 1);
    $("#begin-date").attr('value', date.toISOString().substr(0, 10));
}

function buildUrl(resources, start, end, page_size = 50000, format = 'xlsx') {
    return `${window.location.origin}/v1/reservation/?format=${format}&resource=${resources.join()}&start=${start}&end=${end}&page_size=${page_size}&state=confirmed`;
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



function bindSelectPaginatorItems() {
    $(paginator.items).on('click', () => {
        let resources = $(paginator.items).find('input:checked');
        updateSelectAllButton();
    });
}


function addLoader(element, labelText) {
    $(`
    <div id="ld-spinner" class="col-wrap-container fluid justify-center align-items-center">
        <div class="ld-spinner"></div>
        <label for="ld-spinner" class="control-label input-label small-text align-center">${labelText[SELECTED_LANGUAGE]}</label>
    </div>`
    ).appendTo(element);
}

function removeLoader(element) {
    $(element).find('#ld-spinner').remove();
}

function bindGenerateButton() {
    let btn = $("#generate-btn");
    $(btn).on('click', () => {
        let resources = [];
        $(paginator.items)
            .find('input:checked')
            .each((_, resource) => resources.push($(resource).attr('id')));

        let begin = $("#begin-date").val();
        let end = $("#end-date").val();

        if (new Date(begin) > new Date(end)) {
            alert({
                'fi': 'Alkupäivä ei voi olla suurempi kuin loppupäivä.',
                'en': 'Start date cannot be greater than end date.',
                'sv': 'Startdatum kan inte vara större än slutdatum.'
            }[SELECTED_LANGUAGE]);
            return;
        }

        var http = new XMLHttpRequest();
        http.responseType = 'blob';
        http.onreadystatechange = () => {
            if (http.readyState === 4) {
                switch(http.status) {
                    case 200: {
                        var url = window.URL.createObjectURL(http.response);
                        let dl = document.createElement('a');
                        dl.href = url;
                        dl.download = 'report.xlsx';
                        dl.click();
                        $("body").css("cursor", "default");
                        removeLoader($(btn).parent());
                        $(btn).show();
                        break;
                    }
                    default: { 
                        $("body").css("cursor", "default"); 
                        removeLoader($(btn).parent());
                        $(btn).show();
                        alertPopup({
                            'fi': 'Jotain meni pieleen',
                            'sv': 'Något gick fel',
                            'en': 'Something went wrong',
                        }[SELECTED_LANGUAGE], 'error');
                        break; 
                    }
                }
            }
        }
        http.open('GET', buildUrl(resources, begin, end));
        http.send();
        $("body").css("cursor", "progress");
        addLoader($(btn).parent(), {
            'fi': 'Raporttia luodaan',
            'sv': 'Generating report',
            'en': 'Generating report'
        });
        $(btn).hide();
    });

    setInterval(() => {
        if ($(paginator.items).find('input:checked').length > 0) {
            $(btn).prop('disabled', false);
        } else {
            $(btn).prop('disabled', true);
        }
    }, 200);
}