import {
  addNewImage,
  removeImage,
  updateImagesTotalForms,
} from "./resourceFormImages";

import { initializePeriods } from "./periods";

import { toggleLanguage } from "./resourceFormLanguage";

let emptyImageItem = null;

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
  showSearchTagInput();
  preventContentEditableInitial();
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

export function showSearchTagInput() {
  let newValue = [];
  let tagInput = $(document.getElementById("id_tags"));
  $($(tagInput).val().split(",")).each((index, tag) => {
    let parsed = parseTag(tag);
    if (parsed) {
      newValue.push(parsed);
    }
  });
  $(tagInput).val("");

  if (newValue.length > 0) {
    $(tagInput).attr("type", "text").val(newValue.join(", "));
  }
}

function parseTag(str) {
  let tag = $.trim(str)
    .replace(/[^\w\söäå]/gi, "")
    .match(/^Tag (.*)/);
  if (tag) return tag[1];
  return null;
}

export function preventContentEditableInitial() {
  let emailField = $(document).find("#emails-list-box");
  let emailInput = $(document).find("#staffEmailInput");
  let emailBtn = $(document).find('#appendEmailButton');
  let emailDeleteBtn = $(document).find('#removeEmailSelection');
  let actualField = $(document).find("#id_resource_staff_emails");
  let helpText  = $(document).find('#email-help-text')

  function testValue(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
  }

  function updateListItems() {
    $(emailField).find('li').each((index, item) => {
      $(item).unbind('click');
      $(item).click((f) => {
        if ($(item).hasClass('active')) {
          $(item).removeClass('active');
        } else {
          $(item).addClass('active');
          $(emailDeleteBtn).attr('disabled', false);
        }
      })
    })
  }

  function append(value) {
    if (!testValue(value))
      return;



    $(emailField).append(
      `<li>${value}</li>`
    )

    $(actualField).val(`${actualField.val()}${value}\n`)

    $(emailInput).val('');
    updateListItems();
  }

  function remove(value) {
    let new_val = "";
    $(emailField).find('li').each((index, item) => {
      if ($(item).text() === value) {
        $(item).remove();
      } else {
        new_val = `${new_val}${$(item).text().trim()}\n`
      }
    })
    $(actualField).val(new_val);
  }

  setInterval((f) => {
    if ($(emailInput).val().length > 0) {
      $(emailBtn).attr('disabled', false);
      $.each($(emailInput).val().split(','), (i, value) => {
        if (!testValue(value.trim())) {
          $(emailBtn).attr('disabled', true);
        }
      });
    } else {
      $(emailBtn).attr('disabled', true);
    }
    if ($(emailField).find('li').length === 0) {
      $(helpText).hide();
    } else {
      $(helpText).show();
    }

    if ($(emailField).find('li[class="active"]').length == 0) {
      $(emailDeleteBtn).attr('disabled', true);
    }

  }, 300);

  $(emailInput).on('keydown', (e) => {
    if (e.key == 'Enter') {
      e.preventDefault();
      if ($(emailInput).val().length > 0) {
        $.each($(emailInput).val().split(','), (i, value) => {
          append(value.trim());
        });
      }
    }
  });
  $(emailBtn).click((e) => {
    e.preventDefault();
    if ($(emailInput).val().length > 0) {
      $.each($(emailInput).val().split(','), (i, value) => {
        append(value.trim());
      });
    }
  })

  $(emailDeleteBtn).click((e) => {
    e.preventDefault();
    $(emailField).find('li[class="active"]').each((i, value) => {
      remove($(value).text());
    });
  })

  $(emailDeleteBtn).attr('disabled', true);

  updateListItems();
}