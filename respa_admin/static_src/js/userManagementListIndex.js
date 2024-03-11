import { Paginate } from './utils';


let paginators = [];


function start() {
    handlePagination();
    bindCollapseBtnFx();
    bindUserFilter();
}




function getPaginator(id) {
  return paginators.filter((paginator) => {
    return paginator.id === id;
  })[0];
}



function handlePagination() {
  $("div[data-paginate=true]").each((i, div) => {
    paginators.push(new Paginate(div));
  });
}


function bindUserFilter() {
  $("[id^=user-filter-]").each((_, userFilter) => {
    $(userFilter).on('input', () => {
      let paginator = getPaginator($(userFilter).data('paginator-id'));
      let search = $(userFilter).val();
      search ? paginator.filter(search) : paginator.reset();
    });
  })
}


function bindCollapseBtnFx() {
  let div = $("div[id=permissionCollapse]");
  let span = $("button[id=collapseButton]").find("span");
  if ($(div).hasClass("show")) {
    $(span).removeClass('glyphicon-chevron-down');
    $(span).addClass('glyphicon-chevron-up');
  }

  $("button[id=collapseButton]").on('click', (e) => {
    if ($(span).hasClass("glyphicon-chevron-down")) {
      $(span).removeClass('glyphicon-chevron-down');
      $(span).addClass('glyphicon-chevron-up');
      return;
    }
    if ($(span).hasClass("glyphicon-chevron-up")) {
      $(span).removeClass('glyphicon-chevron-up');
      $(span).addClass('glyphicon-chevron-down');
      return;
    }
  })
}


window.addEventListener('load', start, false);