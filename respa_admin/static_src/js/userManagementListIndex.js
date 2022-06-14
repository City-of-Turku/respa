import { Paginate } from './utils';



function start() {
    handlePagination();
}





function handlePagination() {
    $("div[paginate]").each((i, div) => {
      let paginationId = $(div).attr('paginate');
      let array =  $(div).find('div[array-item]').toArray();
      let perPage = $(div).attr("per-page");
      let pagination = $(div).parent().find(`div[id=pagination-container-${paginationId}]`);
      new Paginate(paginationId, array, perPage, pagination);
    });
  }


window.addEventListener('load', start, false);