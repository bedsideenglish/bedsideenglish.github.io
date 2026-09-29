(function () {
  "use strict";

  var form = document.querySelector("[data-library-filter]");
  var grid = document.querySelector("[data-library-grid]");
  if (!form || !grid) return;

  var input = form.querySelector("[data-library-search]");
  var clearButton = form.querySelector("[data-library-clear]");
  var countNode = form.querySelector("[data-library-count]");
  var empty = document.querySelector("[data-library-empty]");
  var resetButton = empty ? empty.querySelector("[data-library-reset]") : null;
  var chips = Array.prototype.slice.call(form.querySelectorAll("[data-specialty]"));
  var cards = Array.prototype.slice.call(grid.querySelectorAll(".interview-card"));
  if (!input || !cards.length || !chips.length) return;

  var total = cards.length;
  var specialty = "";
  var query = "";

  // Accent- and punctuation-insensitive so "obgyn", "OB/GYN", and "ob gyn" all reach the same
  // cards, and so a pasted term with a stray comma still matches.
  function normalize(value) {
    var text = String(value).toLowerCase();
    if (text.normalize) text = text.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    return text.replace(/[^a-z0-9]+/g, " ").trim();
  }

  var haystacks = cards.map(function (card) {
    return normalize(card.getAttribute("data-search") || "");
  });

  function terms() {
    var normalized = normalize(query);
    return normalized ? normalized.split(" ") : [];
  }

  function matchesQuery(index, tokens) {
    for (var i = 0; i < tokens.length; i += 1) {
      if (haystacks[index].indexOf(tokens[i]) === -1) return false;
    }
    return true;
  }

  // The model follow-up hub reuses this script, so the noun comes from the form when it is set.
  var nounOne = form.getAttribute("data-noun-one") || "history";
  var nounMany = form.getAttribute("data-noun-many") || "histories";

  function describe(shown) {
    if (!shown) return "No " + nounOne + " matches yet";
    if (shown === total) return "Showing all " + total + " " + nounMany;
    return "Showing " + shown + " of " + total + " " + nounMany;
  }

  // Chip counts follow the keyword search but not the chosen specialty, so the numbers always
  // answer "what would I get if I pressed this instead?".
  function updateChips(tokens) {
    var perSpecialty = {};
    var queryMatches = 0;
    cards.forEach(function (card, index) {
      if (!matchesQuery(index, tokens)) return;
      var name = card.getAttribute("data-specialty") || "";
      perSpecialty[name] = (perSpecialty[name] || 0) + 1;
      queryMatches += 1;
    });
    chips.forEach(function (chip) {
      var name = chip.getAttribute("data-specialty");
      var value = name ? perSpecialty[name] || 0 : queryMatches;
      var counter = chip.querySelector("[data-chip-count]");
      if (counter) counter.textContent = String(value);
      chip.setAttribute("aria-pressed", name === specialty ? "true" : "false");
      // The active chip stays clickable even at zero so the reader can always press back out.
      chip.disabled = value === 0 && name !== specialty;
    });
  }

  function syncUrl() {
    if (!window.history || !window.history.replaceState || !window.URLSearchParams) return;
    var params = new URLSearchParams(window.location.search);
    if (query) params.set("q", query); else params.delete("q");
    if (specialty) params.set("specialty", specialty); else params.delete("specialty");
    var search = params.toString();
    window.history.replaceState(null, "", window.location.pathname + (search ? "?" + search : "") + window.location.hash);
  }

  function apply() {
    var tokens = terms();
    var shown = 0;
    cards.forEach(function (card, index) {
      var visible = (!specialty || card.getAttribute("data-specialty") === specialty) && matchesQuery(index, tokens);
      card.hidden = !visible;
      if (visible) shown += 1;
    });
    updateChips(tokens);
    if (countNode) countNode.textContent = describe(shown);
    if (empty) empty.hidden = shown !== 0;
    if (clearButton) clearButton.hidden = !query;
    grid.hidden = shown === 0;
  }

  function setQuery(value, fromInput) {
    query = value.trim();
    if (!fromInput) input.value = value;
    apply();
    syncUrl();
  }

  function setSpecialty(value) {
    specialty = value;
    apply();
    syncUrl();
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
  });

  input.addEventListener("input", function () {
    setQuery(input.value, true);
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && input.value) {
      event.preventDefault();
      setQuery("", false);
    }
  });

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      var name = chip.getAttribute("data-specialty");
      setSpecialty(name === specialty ? "" : name);
    });
  });

  if (clearButton) {
    clearButton.addEventListener("click", function () {
      setQuery("", false);
      input.focus();
    });
  }

  if (resetButton) {
    resetButton.addEventListener("click", function () {
      specialty = "";
      setQuery("", false);
      input.focus();
    });
  }

  // A shared link should land on the same shortlist the sender was looking at.
  if (window.URLSearchParams) {
    var params = new URLSearchParams(window.location.search);
    var savedQuery = params.get("q") || "";
    var savedSpecialty = params.get("specialty") || "";
    if (savedQuery) {
      query = savedQuery.trim();
      input.value = savedQuery;
    }
    if (savedSpecialty && chips.some(function (chip) { return chip.getAttribute("data-specialty") === savedSpecialty; })) {
      specialty = savedSpecialty;
    }
  }

  form.hidden = false;
  apply();
})();
