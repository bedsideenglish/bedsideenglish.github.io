(function (global) {
  "use strict";

  var UNCERTAIN = /\b(?:maybe|perhaps|possibly|probably|either|unsure|uncertain|guess|guessing)\b/i;
  var NEGATED = /\b(?:not|no|never|wrong|incorrect)\b/i;

  function normalize(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/[’']/g, "")
      .replace(/n't\b/g, " not")
      .replace(/[^a-z0-9]+/g, " ")
      .trim()
      .replace(/\s+/g, " ");
  }

  function containsPhrase(haystack, needle) {
    if (!needle) return false;
    return (" " + haystack + " ").indexOf(" " + needle + " ") !== -1;
  }

  function scoreField(value, acceptedAnswers) {
    var raw = String(value || "").trim();
    var answer = normalize(raw);
    if (!answer) return { correct: false, reason: "empty", matched: null };
    if (UNCERTAIN.test(raw) || /\b(?:or)\b/i.test(raw) || raw.indexOf("/") !== -1) {
      return { correct: false, reason: "alternative_list", matched: null };
    }
    if (NEGATED.test(raw)) {
      return { correct: false, reason: "negated", matched: null };
    }

    var accepted = (acceptedAnswers || []).map(function (item) {
      return { raw: String(item), normalized: normalize(item) };
    }).filter(function (item) { return item.normalized; });

    for (var i = 0; i < accepted.length; i += 1) {
      var candidate = accepted[i];
      if (answer === candidate.normalized || containsPhrase(answer, candidate.normalized)) {
        return { correct: true, reason: null, matched: candidate.raw };
      }
    }
    return { correct: false, reason: "not_found", matched: null };
  }

  function scoreDetails(details, answers) {
    var results = (details || []).map(function (detail) {
      var result = scoreField(answers[detail.key], detail.answers);
      return {
        key: detail.key,
        label: detail.label || detail.key,
        correct: result.correct,
        reason: result.reason,
        matched: result.matched,
        accepted_answers: detail.answers || []
      };
    });
    var correct = results.filter(function (result) { return result.correct; }).length;
    return {
      details_correct: correct,
      details_total: results.length,
      accuracy: results.length ? correct / results.length : 0,
      detail_results: results
    };
  }

  function selectVoice(profile, voices) {
    var pool = (voices || []).filter(function (voice) { return /^en(?:-|$)/i.test(voice.lang || ""); });
    var candidates = (profile && profile.lang_candidates) || ["en-US"];
    for (var i = 0; i < candidates.length; i += 1) {
      var exact = pool.find(function (voice) {
        return String(voice.lang || "").toLowerCase() === candidates[i].toLowerCase();
      });
      if (exact) return exact;
    }
    for (var j = 0; j < candidates.length; j += 1) {
      var base = candidates[j].split("-")[0].toLowerCase();
      var sameLanguage = pool.find(function (voice) {
        return String(voice.lang || "").toLowerCase().split("-")[0] === base;
      });
      if (sameLanguage) return sameLanguage;
    }
    return pool[0] || (voices || [])[0] || null;
  }

  function reasonText(reason) {
    if (reason === "empty") return "No answer was entered.";
    if (reason === "alternative_list") return "Commit one value after you confirm it; do not list alternatives as the answer.";
    if (reason === "negated") return "The matching value was negated, so it was not counted.";
    return "No confident match was found.";
  }

  function init(root) {
    var configNode = root.querySelector("#listening-lab-config");
    if (!configNode) return;
    var config;
    try {
      config = JSON.parse(configNode.textContent);
    } catch (error) {
      return;
    }

    var synth = global.speechSynthesis;
    var profileSelect = root.querySelector("#accent-profile");
    var voiceStatus = root.querySelector("#voice-status");
    var playButton = root.querySelector("#play-clip");
    var repeatButton = root.querySelector("#repeat-clip");
    var slowButton = root.querySelector("#slow-clip");
    var commitButton = root.querySelector("#commit-answer");
    var resetButton = root.querySelector("#try-again");
    var form = root.querySelector("#listening-answer-form");
    var resultPanel = root.querySelector("#listening-result");
    var resultHeadline = root.querySelector("#result-headline");
    var resultMeta = root.querySelector("#result-meta");
    var transcript = root.querySelector("#revealed-transcript");
    var liveStatus = root.querySelector("#lab-status");
    var progress = root.querySelector("#local-progress");
    var voices = [];
    var currentAudio = null;
    var state = { plays: 0, replays: 0, slowReplays: 0, repairs: [], submitted: false };

    function refreshVoices() {
      voices = synth ? synth.getVoices() : [];
      updateVoiceStatus();
    }

    function currentProfile() {
      var selected = profileSelect ? profileSelect.value : "us";
      return (config.profiles || []).find(function (profile) { return profile.id === selected; }) || config.profiles[0];
    }

    function updateVoiceStatus() {
      if (!voiceStatus) return;
      var profile = currentProfile();
      var reviewedSource = config.drill.audio_sources && config.drill.audio_sources[profile.id];
      var audioAvailable = Boolean(reviewedSource);
      var browserAvailable = Boolean(synth && typeof global.SpeechSynthesisUtterance === "function");
      [playButton, repeatButton, slowButton].forEach(function (button) {
        if (button && !state.submitted) button.disabled = !(audioAvailable || browserAvailable);
      });
      if (reviewedSource) {
        voiceStatus.textContent = "Reviewed, pre-generated audio is available for " + profile.label + ".";
        return;
      }
      if (!synth || typeof global.SpeechSynthesisUtterance !== "function") {
        voiceStatus.textContent = "Audio is unavailable in this browser. You can still use the response guide below.";
        return;
      }
      var voice = selectVoice(profile, voices);
      if (voice) {
        var exact = (profile.lang_candidates || []).some(function (lang) {
          return String(voice.lang).toLowerCase() === String(lang).toLowerCase();
        });
        voiceStatus.textContent = exact
          ? "Browser voice: " + voice.name + " (" + voice.lang + ")."
          : "Generic English fallback: " + voice.name + " (" + voice.lang + "). This browser does not provide an exact profile match.";
      } else {
        voiceStatus.textContent = "Your browser will choose its default English voice.";
      }
    }

    function speak(rate, repair) {
      if (state.submitted || (synth && synth.speaking) || (currentAudio && !currentAudio.paused)) return;
      var profile = currentProfile();
      var reviewedSource = config.drill.audio_sources && config.drill.audio_sources[profile.id];
      if (!reviewedSource && !synth) return;
      state.plays += 1;
      if (state.plays > 1) state.replays += 1;
      if (rate < 1) state.slowReplays += 1;
      if (repair && state.repairs.indexOf(repair) === -1) state.repairs.push(repair);
      liveStatus.textContent = rate < 1 ? "Playing the same message more slowly…" : "Playing the message…";
      playButton.setAttribute("aria-pressed", "true");

      if (reviewedSource) {
        currentAudio = new global.Audio(reviewedSource);
        currentAudio.playbackRate = rate;
        if ("preservesPitch" in currentAudio) currentAudio.preservesPitch = true;
        currentAudio.onended = function () {
          liveStatus.textContent = "Audio finished. Commit the details you heard.";
          playButton.setAttribute("aria-pressed", "false");
        };
        currentAudio.onerror = function () {
          liveStatus.textContent = "The reviewed clip could not be loaded. Choose another profile to use a browser voice.";
          playButton.setAttribute("aria-pressed", "false");
        };
        currentAudio.play().catch(function () {
          liveStatus.textContent = "The browser blocked audio playback. Press play again.";
          playButton.setAttribute("aria-pressed", "false");
        });
        return;
      }

      var voice = selectVoice(profile, voices);
      var utterance = new global.SpeechSynthesisUtterance(config.drill.transcript);
      utterance.rate = rate;
      utterance.pitch = 1;
      if (voice) {
        utterance.voice = voice;
        utterance.lang = voice.lang;
      } else {
        utterance.lang = (profile.lang_candidates || ["en-US"])[0];
      }
      utterance.onend = function () {
        liveStatus.textContent = "Audio finished. Commit the details you heard.";
        playButton.setAttribute("aria-pressed", "false");
      };
      utterance.onerror = function () {
        liveStatus.textContent = "The browser could not play this voice. Try another profile or use the written guide below.";
        playButton.setAttribute("aria-pressed", "false");
      };
      synth.speak(utterance);
    }

    function readAnswers() {
      var answers = {};
      (config.drill.details || []).forEach(function (detail) {
        var field = form.elements.namedItem(detail.key);
        answers[detail.key] = field ? field.value.trim() : "";
      });
      return answers;
    }

    function saveAttempt(score) {
      var key = "bedsideEnglishEverydayListeningAttempts";
      var attempts = [];
      try { attempts = JSON.parse(global.localStorage.getItem(key) || "[]"); } catch (error) { attempts = []; }
      attempts.push({
        drill_id: config.drill.id,
        created_at: new Date().toISOString(),
        details_correct: score.details_correct,
        details_total: score.details_total,
        unaided: state.replays === 0 && state.slowReplays === 0,
        replay_count: state.replays,
        slow_replay_count: state.slowReplays,
        repairs: state.repairs.slice(),
        profile: currentProfile().id
      });
      try { global.localStorage.setItem(key, JSON.stringify(attempts.slice(-20))); } catch (error) { /* Private mode may block storage. */ }
      renderProgress(attempts);
    }

    function renderProgress(attempts) {
      if (!progress) return;
      var relevant = (attempts || []).filter(function (attempt) { return attempt.drill_id === config.drill.id; });
      if (!relevant.length) {
        progress.textContent = "No attempts saved on this device yet.";
        return;
      }
      var correct = relevant.reduce(function (sum, attempt) { return sum + Number(attempt.details_correct || 0); }, 0);
      var total = relevant.reduce(function (sum, attempt) { return sum + Number(attempt.details_total || 0); }, 0);
      var unaided = relevant.filter(function (attempt) { return attempt.unaided; }).length;
      progress.textContent = relevant.length + " local attempt" + (relevant.length === 1 ? "" : "s") + " · " + correct + "/" + total + " exact details · " + unaided + " unaided";
    }

    function renderScore(score) {
      state.submitted = true;
      synth && synth.cancel();
      if (currentAudio) { currentAudio.pause(); currentAudio.currentTime = 0; }
      profileSelect.disabled = true;
      [playButton, repeatButton, slowButton, commitButton].forEach(function (button) { if (button) button.disabled = true; });
      (config.drill.details || []).forEach(function (detail) {
        var field = form.elements.namedItem(detail.key);
        var result = score.detail_results.find(function (item) { return item.key === detail.key; });
        if (!field || !result) return;
        field.disabled = true;
        var row = field.closest(".answer-field");
        var feedback = row && row.querySelector(".field-feedback");
        if (row) row.classList.add(result.correct ? "is-correct" : "is-incorrect");
        if (feedback) {
          feedback.hidden = false;
          feedback.textContent = result.correct
            ? "Correct — " + result.matched
            : reasonText(result.reason) + " Accepted: " + result.accepted_answers.slice(0, 3).join(", ");
        }
      });
      var perfect = score.details_correct === score.details_total;
      resultHeadline.textContent = perfect ? "You caught every exact detail." : "You caught " + score.details_correct + " of " + score.details_total + " details.";
      var mode = state.replays === 0 && state.slowReplays === 0 ? "Unaided first listen" : "Assisted repair";
      resultMeta.textContent = mode + " · " + state.replays + " replay" + (state.replays === 1 ? "" : "s") + (state.repairs.length ? " · practiced " + state.repairs.join(" + ") : "");
      transcript.textContent = config.drill.transcript;
      resultPanel.hidden = false;
      resultPanel.focus();
      saveAttempt(score);
    }

    function reset() {
      synth && synth.cancel();
      if (currentAudio) { currentAudio.pause(); currentAudio.currentTime = 0; currentAudio = null; }
      state = { plays: 0, replays: 0, slowReplays: 0, repairs: [], submitted: false };
      profileSelect.disabled = false;
      [playButton, repeatButton, slowButton, commitButton].forEach(function (button) { if (button) button.disabled = false; });
      (config.drill.details || []).forEach(function (detail) {
        var field = form.elements.namedItem(detail.key);
        if (!field) return;
        field.disabled = false;
        field.value = "";
        var row = field.closest(".answer-field");
        var feedback = row && row.querySelector(".field-feedback");
        if (row) row.classList.remove("is-correct", "is-incorrect");
        if (feedback) { feedback.hidden = true; feedback.textContent = ""; }
      });
      resultPanel.hidden = true;
      liveStatus.textContent = "Ready. Play the message once, then commit what you heard.";
      updateVoiceStatus();
      playButton.focus();
    }

    if (profileSelect) profileSelect.addEventListener("change", updateVoiceStatus);
    if (playButton) playButton.addEventListener("click", function () {
      if ((synth && synth.speaking) || (currentAudio && !currentAudio.paused)) {
        if (synth) synth.cancel();
        if (currentAudio) { currentAudio.pause(); currentAudio.currentTime = 0; }
        liveStatus.textContent = "Audio stopped.";
        playButton.setAttribute("aria-pressed", "false");
      } else {
        speak(1, null);
      }
    });
    if (repeatButton) repeatButton.addEventListener("click", function () { speak(1, "repeat"); });
    if (slowButton) slowButton.addEventListener("click", function () { speak(0.78, "slow"); });
    if (form) form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (state.submitted) return;
      var answers = readAnswers();
      if (!Object.keys(answers).some(function (key) { return answers[key]; })) {
        liveStatus.textContent = "Type at least one detail before committing your answer.";
        form.querySelector("input") && form.querySelector("input").focus();
        return;
      }
      renderScore(scoreDetails(config.drill.details, answers));
    });
    if (resetButton) resetButton.addEventListener("click", reset);

    refreshVoices();
    if (synth) synth.addEventListener && synth.addEventListener("voiceschanged", refreshVoices);
    var existing = [];
    try { existing = JSON.parse(global.localStorage.getItem("bedsideEnglishEverydayListeningAttempts") || "[]"); } catch (error) { existing = []; }
    renderProgress(existing);
  }

  var api = { normalize: normalize, scoreField: scoreField, scoreDetails: scoreDetails, selectVoice: selectVoice };
  global.BedsideListeningLab = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (global.document) {
    global.document.addEventListener("DOMContentLoaded", function () {
      var root = global.document.querySelector("[data-listening-lab]");
      if (root) init(root);
    });
  }
})(typeof window !== "undefined" ? window : globalThis);
