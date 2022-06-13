export function alertPopup(message, type = 'success') {
    let popup = $("div[id=popup-notification]");
    let popupSpan = $(popup).find('span[id=popup-message]');

    switch(type) {
        case 'success':
            $(popup).addClass('success');
        break;
        case 'error':
            $(popup).addClass('error');
        break;
        default:
        break
    }

    $(popupSpan).text(message);
    $(popup).fadeIn('slow').css('display', 'flex');

    setTimeout(() => {
        $(popup).fadeOut('slow');
        setTimeout(() => {
        $(popupSpan).text('');
        }, 500);
    }, 5000);
}



export class Paginate {
    constructor(id, array, perPage, paginationContainer) {
        this.id = id;
        this.array = array.reduce((arr, val, i) => {
            let idx = Math.floor(i / perPage);
            let page = arr[idx] || (arr[idx] = []);
            page.push(val);
            return arr;
        }, []);
        this.hide(this.array);
        this.page = 0;
        this.paginationContainer = paginationContainer;
        this.totalPages = this.array.length;
        this.show(this.current());
    }

    update() {
        if (this.totalPages > 1) {
            if ($(this.paginationContainer).find(`a[id=next_page_${this.id}]`).length === 0) {
                $(`<a href=\"#\" id=\"next_page_${this.id}\">\>\></a>`)
                .appendTo(this.paginationContainer)
                .on('click', (e) => {
                    e.preventDefault();
                    $(this.current()).hide();
                    $(this.next()).show();
                });
            }
        }
        if (!this.hasNextPage()) $(this.paginationContainer).find(`a[id=next_page_${this.id}]`).remove();
        if (this.page > 0) {
            if ($(this.paginationContainer).find(`a[id=prev_page_${this.id}]`).length === 0) {
                $(`<a href=\"#\" id=\"prev_page_${this.id}\">\<\<</a>`)
                .prependTo(this.paginationContainer)
                .on('click', (e) => {
                    e.preventDefault();
                    $(this.current()).hide();
                    $(this.previous()).show();
                });
            }
        } else $(this.paginationContainer).find(`a[id=prev_page_${this.id}]`).remove();

        $(this.paginationContainer).find('span').text(`${
            {'fi': 'Sivu', 'en': 'Page', 'sv': 'Page'}[$('html').attr('lang')]
        }: ${this.page + 1}`);
    }

    hasNextPage() {
        return this.array[this.page + 1] !== undefined && this.array[this.page + 1].length > 0;
    }

    next() {
        this.page++;
        this.update();
        return this.array[this.page];
    }

    previous() {
        this.page--;
        this.update();
        return this.array[this.page];
    }

    current() {
        this.update();
        return this.array[this.page];
    }

    show(array) {
        array.forEach((item) => {
            $(item).show();
        });
    }

    hide(array) {
        array.forEach((item) => {
            $(item).hide();
        });
    }
}