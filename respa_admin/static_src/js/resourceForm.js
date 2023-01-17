import {
  addNewImage,
  removeImage,
  updateImagesTotalForms,
} from "./resourceFormImages";

import { alertPopup, getErrorMessage } from './utils';

import { initializePeriods } from "./periods";

import { toggleLanguage } from "./resourceFormLanguage";

let emptyImageItem = null;
const SELECTED_LANGUAGE = $('html').attr('lang');

export function initializeResourceForm() {
  initializeEventHandlers();
  initializePeriods();
  setImageItem();
}

/*
 * Attach all the event handlers to their objects upon load.
 * */
export function initializeEventHandlers() {
  enableLanguageButtons();
  enableAddNewImage();
  enableRemoveImage();
  resourceStaffEmailsHandler();
  resourceTagsHandler();
  bindSoftDelete();
}

export function getEmptyImage() {
  return emptyImageItem;
}

/*
 * Setter for the empty image item which is may
 * be used for creating new image items in the DOM.
 * */
function setImageItem() {
  //Get the last image.
  let $imageList = $("#images-list")[0].children;
  let $servedImageItem = $imageList[$imageList.length - 1];

  //Clone it.
  emptyImageItem = $($servedImageItem).clone();

  //Remove it from the DOM.
  $servedImageItem.remove();

  //The image list is hidden by default in order to avoid
  //Image flashing when loading the page. Remove the hidden attribute.
  $("#images-list")[0].classList.remove("hidden");

  updateImagesTotalForms();
}

/*
 * Bind event for adding images.
 * */
function enableAddNewImage() {
  let imagePicker = document.getElementById("image-picker");
  imagePicker.addEventListener("click", addNewImage, false);
}

/*
 * Bind events for removing an image.
 * */
function enableRemoveImage() {
  let images = document.getElementById("images-list").children;

  for (let i = 0; i < images.length; i++) {
    let removeButton = document.getElementById("remove-image-" + i);
    let imageItem = $("#image-" + i);
    removeButton.addEventListener("click", () => removeImage(imageItem), false);
  }
}

/*
 * Bind event for hiding/showing translated fields in form.
 * */
function enableLanguageButtons() {
  let languageSwitcher = document.getElementsByClassName("language-switcher");
  let languagesAmount = languageSwitcher[0].children.length;

  for (let i = 0; i < languagesAmount; i++) {
    let languageButton = languageSwitcher[0].children[i];
    let language = languageButton.value;
    languageButton.addEventListener(
      "click",
      () => toggleLanguage(language),
      false
    );
  }
}

export function calendarHandler() {
  // Copied from bootstrap-datepicker@1.8.0/js/locales/bootstrap-datepicker.fi.js
  // As it can not be imported as a module, and would need to be shimmed
  $.fn.datepicker.dates["fi"] = {
    days: [
      "sunnuntai",
      "maanantai",
      "tiistai",
      "keskiviikko",
      "torstai",
      "perjantai",
      "lauantai",
    ],
    daysShort: ["sun", "maa", "tii", "kes", "tor", "per", "lau"],
    daysMin: ["su", "ma", "ti", "ke", "to", "pe", "la"],
    months: [
      "tammikuu",
      "helmikuu",
      "maaliskuu",
      "huhtikuu",
      "toukokuu",
      "kesäkuu",
      "heinäkuu",
      "elokuu",
      "syyskuu",
      "lokakuu",
      "marraskuu",
      "joulukuu",
    ],
    monthsShort: [
      "tam",
      "hel",
      "maa",
      "huh",
      "tou",
      "kes",
      "hei",
      "elo",
      "syy",
      "lok",
      "mar",
      "jou",
    ],
    today: "tänään",
    clear: "Tyhjennä",
    weekStart: 1,
    format: "d.m.yyyy",
  };
}

/*
 * Inject class to display colored ball in a dropdown
 */
export function addDropdownColor() {
  let publicDropdown = document.getElementById("id_public");
  let publicDropdownValue =
    publicDropdown.options[publicDropdown.selectedIndex].value;
  let publicDropdownIcon = document.getElementById("public-dropdown-icon");

  let reservableDropdown = document.getElementById("id_reservable");
  let reservableDropdownValue =
    reservableDropdown.options[reservableDropdown.selectedIndex].value;
  let reservableDropdownIcon = document.getElementById(
    "reservable-dropdown-icon"
  );

  if (publicDropdownValue === "True") {
    publicDropdownIcon.className = "shape-success";
  } else {
    publicDropdownIcon.className = "shape-warning";
  }

  if (reservableDropdownValue === "True") {
    reservableDropdownIcon.className = "shape-success";
  } else {
    reservableDropdownIcon.className = "shape-danger";
  }
}

/*
 * Listener to change the color of the color-coding ball when change happens
 */
export function coloredDropdownListener(event) {
  let publicDropdown = document.getElementById("id_public");
  let reservableDropdown = document.getElementById("id_reservable");
  publicDropdown.addEventListener("change", addDropdownColor, false);
  reservableDropdown.addEventListener("change", addDropdownColor, false);
}

function updateListItems(field, deleteBtn) {
  if ($(field).attr('disabled'))
    return;
  $(field).find('li').each((index, item) => {
    $(item).unbind('click');
    $(item).click((f) => {
      if ($(item).hasClass('active')) {
        $(item).removeClass('active');
      } else {
        $(item).addClass('active');
        $(deleteBtn).attr('disabled', false);
      }
    })
  })
}

function resourceStaffEmailsHandler() {
  let field = $(document).find("#emails-list-box");
  let input = $(document).find("#staffEmailInput");
  let btn = $(document).find('#appendEmailButton');
  let deleteBtn = $(document).find('#removeEmailSelection');
  let actualField = $(document).find("#id_resource_staff_emails");
  let helpText  = $(document).find('#email-help-text')

  function testValue(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
  }

  function append(value) {
    if (!testValue(value))
      return;
    $(field).append(
      `<li>${value}</li>`
    )
    $(actualField).val(`${actualField.val()}${value}\n`)
    $(input).val('');
    updateListItems(field, deleteBtn);
  }

  function remove(value) {
    let new_val = "";
    $(field).find('li').each((index, item) => {
      if ($(item).text() === value) {
        $(item).remove();
      } else {
        new_val = `${new_val}${$(item).text().trim()}\n`
      }
    })
    $(actualField).val(new_val);
  }

  setInterval((f) => {
    if ($(input).val().length > 0) {
      $(btn).attr('disabled', false);
      $.each($(input).val().split(','), (i, value) => {
        if (!testValue(value.trim())) {
          $(btn).attr('disabled', true);
        }
      });
    } else {
      $(btn).attr('disabled', true);
    }
    if ($(field).find('li').length === 0) {
      $(helpText).hide();
    } else {
      $(helpText).show();
    }

    if ($(field).find('li[class="active"]').length == 0) {
      $(deleteBtn).attr('disabled', true);
    }
  }, 300);

  $(input).on('keydown', (e) => {
    if (e.key == 'Enter') {
      e.preventDefault();
      if ($(input).val().length > 0) {
        $.each($(input).val().split(','), (i, value) => {
          append(value.trim());
        });
      }
    }
  });
  $(btn).click((e) => {
    e.preventDefault();
    if ($(input).val().length > 0) {
      $.each($(input).val().split(','), (i, value) => {
        append(value.trim());
      });
    }
  })

  $(deleteBtn).click((e) => {
    e.preventDefault();
    $(field).find('li[class="active"]').each((i, value) => {
      remove($(value).text());
    });
  })

  $(deleteBtn).attr('disabled', true);

  updateListItems(field, deleteBtn);
}


function resourceTagsHandler() {
  let field = $(document).find("#tags-list-box");
  let input = $(document).find("#tagInput");
  let deleteBtn = $(document).find('#removeTagSelection');
  let btn = $(document).find('#appendTagButton');
  let actualField = $(document).find("#id_resource_tags");

  function append(value) { 
      $(field).append(
        `<li>${value}</li>`
      )
      $(actualField).val(`${actualField.val()}create_${value}\n`);
      $(input).val('');
      updateListItems(field, deleteBtn);
  }
  function remove(value) {
    let new_val = "";
    $(field).find('li').each((index, item) => {
      if ($(item).text() === value) {
        new_val = $(actualField).val((index, text) => {
          return text.replace(`create_${value.trim()}`, `remove_${value.trim()}`);
        }).val()
        $(item).remove();
      }
    })
  }


  $(input).on('keydown', (e) => {
    if (e.key == 'Enter') {
      e.preventDefault();
      if ($(input).val().length > 0) {
        $.each($(input).val().split(','), (i, value) => {
          if (/\s/.test(value)) {
            $.each(value.trim().split(' '), (i, v) => {
              append(v.trim());
            });
          } else {
            append(value.trim());
          }
        });
      }
    }
  });
  $(btn).click((e) => {
    e.preventDefault();
    if ($(input).val().length > 0) {
      $.each($(input).val().split(','), (i, value) => {
        if (/\s/.test(value)) {
          $.each(value.trim().split(' '), (i, v) => {
            append(v.trim());
          });
        } else {
          append(value.trim());
        }
      });
    }
  })

  $(deleteBtn).click((e) => {
    e.preventDefault();
    $(field).find('li[class="active"]').each((i, value) => {
      remove($(value).text());
    });
  })

  setInterval((f) => {
    if ($(input).val().length > 0) {
      $(btn).attr('disabled', false);
    } else {
      $(btn).attr('disabled', true);
    }

    if ($(field).find('li[class="active"]').length == 0) {
      $(deleteBtn).attr('disabled', true);
    }
  }, 300);


  $(deleteBtn).attr('disabled', true);
  updateListItems(field, deleteBtn);
}


function bindSoftDelete() {
  let softDeleteBtn = $('button[id=soft-delete-resource]');
  let form = $(softDeleteBtn).parents('form').first();
  $(softDeleteBtn).on('click', (e) => {
    e.preventDefault();
    if (!confirm({
      'fi': 'Resurssin voi palauttaa myöhemmin, jatketaanko?',
      'sv': 'Resursen kan återställas senare, fortsätt?',
      'en': 'Resource can still be restored after, continue?'
    }[SELECTED_LANGUAGE]))
      return;
    let csrf_token = $(form).find('input[name=csrfmiddlewaretoken]');
    let resourcePk = $(softDeleteBtn).data('pk');

    let softDeleteUrl = `${window.location.origin}/ra/resource/delete`;
    $.ajax({
      'type': 'POST',
      'url': `${softDeleteUrl}/${resourcePk}/`,
      'beforeSend': (xhr) => {
        xhr.setRequestHeader("X-CSRFToken", csrf_token.val());
      },
      'success': (response) => {
        window.location.href = `${window.location.origin}/ra/`;
      },
      'error': (response) => {
        alertPopup(getErrorMessage(response), 'error');
      },
  });
  })
}