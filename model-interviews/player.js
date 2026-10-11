(function () {
  "use strict";

  document.querySelectorAll("[data-conversation-player]").forEach(function (player) {
    var configNode = player.querySelector("[data-audio-config]");
    if (!configNode) return;
    var config;
    try { config = JSON.parse(configNode.textContent); } catch (_) { return; }
    if (!Array.isArray(config.segments) || !config.segments.length) return;

    var playButton = player.querySelector("[data-play]");
    var playLabel = player.querySelector("[data-play-label]");
    var restartButton = player.querySelector("[data-restart]");
    var speedInput = player.querySelector("[data-speed]");
    var speedValue = player.querySelector("[data-speed-value]");
    var progress = player.querySelector("[data-progress]");
    var status = player.querySelector("[data-status]");
    var predictionToggle = player.querySelector("[data-prediction-toggle]");
    var predictionCue = player.querySelector("[data-prediction-cue]");
    var predictionPrompt = player.querySelector("[data-prediction-prompt]");
    var continueButton = player.querySelector("[data-continue]");
    var turns = Array.prototype.slice.call(document.querySelectorAll("[data-transcript] .turn"));
    var transcriptTarget = document.getElementById("conversation") || document.querySelector("[data-transcript]");
    var reduceMotion = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false;
    var audio = new Audio();
    audio.preload = "metadata";
    var segmentIndex = 0;
    var completedSeconds = 0;
    var shouldContinue = false;
    var finished = false;
    var awaitingPrediction = false;

    function currentSpeed() {
      var rate = speedInput ? Number(speedInput.value) : 1;
      return rate > 0 ? rate : 1;
    }

    function scrollTo(element, block) {
      if (!element || typeof element.scrollIntoView !== "function") return;
      element.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: block });
    }

    function scrollToTranscript() {
      if (!transcriptTarget) return;
      var rect = transcriptTarget.getBoundingClientRect();
      var alreadyReading = rect.top < window.innerHeight * 0.6 && rect.bottom > window.innerHeight * 0.25;
      if (alreadyReading) return;
      scrollTo(transcriptTarget, "start");
    }

    function predictionAfter(index) {
      if (!predictionToggle || !predictionToggle.checked || !Array.isArray(config.prediction_pauses)) return null;
      return config.prediction_pauses.find(function (pause) { return Number(pause.after_segment) === index + 1; }) || null;
    }

    function hidePrediction() {
      awaitingPrediction = false;
      if (predictionCue) predictionCue.hidden = true;
    }

    function showPrediction(pause) {
      awaitingPrediction = true;
      shouldContinue = false;
      setPlaying(false);
      if (predictionPrompt) predictionPrompt.textContent = pause.prompt;
      if (predictionCue) {
        predictionCue.hidden = false;
        scrollTo(predictionCue, "center");
      }
      status.textContent = "Paused for your prediction.";
      if (continueButton) continueButton.focus({ preventScroll: true });
    }

    function totalDuration() {
      return config.segments.reduce(function (sum, segment) { return sum + Number(segment.duration_seconds || 0); }, 0);
    }

    function clearActive() {
      turns.forEach(function (turn) { turn.classList.remove("is-active"); });
    }

    function activateSegment(index) {
      clearActive();
      var segment = config.segments[index];
      if (!segment) return;
      for (var i = segment.turn_start; i <= segment.turn_end; i += 1) {
        if (turns[i]) turns[i].classList.add("is-active");
      }
    }

    function setPlaying(playing) {
      player.classList.toggle("is-playing", playing);
      playButton.setAttribute("aria-pressed", String(playing));
      playLabel.textContent = playing ? "Pause" : "Play conversation";
      playButton.querySelector("[aria-hidden]").textContent = playing ? "Ⅱ" : "▶";
    }

    function loadSegment(index) {
      segmentIndex = index;
      var segment = config.segments[index];
      audio.src = segment.file;
      audio.playbackRate = currentSpeed();
      activateSegment(index);
      status.textContent = "Part " + (index + 1) + " of " + config.segments.length + ": following highlighted lines.";
    }

    function playCurrent() {
      shouldContinue = true;
      if (awaitingPrediction) {
        hidePrediction();
        loadSegment(segmentIndex + 1);
      }
      if (finished) {
        finished = false;
        completedSeconds = 0;
        loadSegment(0);
        audio.currentTime = 0;
      }
      if (!audio.src) loadSegment(segmentIndex);
      audio.playbackRate = currentSpeed();
      var started = audio.play();
      if (started && typeof started.catch === "function") {
        started.catch(function () { status.textContent = "Playback could not start. Try pressing play again."; setPlaying(false); });
      }
    }

    function playFromUser() {
      playCurrent();
      scrollToTranscript();
    }

    playButton.addEventListener("click", function () {
      if (!audio.paused) {
        shouldContinue = false;
        audio.pause();
      } else {
        playFromUser();
      }
    });

    restartButton.addEventListener("click", function () {
      audio.pause();
      hidePrediction();
      finished = false;
      completedSeconds = 0;
      loadSegment(0);
      audio.currentTime = 0;
      progress.style.width = "0%";
      playFromUser();
    });

    function syncSpeed() {
      var rate = currentSpeed();
      audio.playbackRate = rate;
      var label = rate.toFixed(2) + "×";
      if (speedValue) speedValue.textContent = label;
      if (speedInput) speedInput.setAttribute("aria-valuetext", label);
    }

    if (speedInput) {
      speedInput.addEventListener("input", syncSpeed);
      syncSpeed();
    }
    if (continueButton) continueButton.addEventListener("click", playFromUser);
    if (predictionToggle) predictionToggle.addEventListener("change", function () {
      if (!predictionToggle.checked && awaitingPrediction) playCurrent();
    });
    audio.addEventListener("play", function () { setPlaying(true); });
    audio.addEventListener("pause", function () { setPlaying(false); });
    audio.addEventListener("timeupdate", function () {
      var total = totalDuration();
      if (total > 0) progress.style.width = Math.min(100, ((completedSeconds + audio.currentTime) / total) * 100) + "%";
    });
    audio.addEventListener("ended", function () {
      completedSeconds += Number(config.segments[segmentIndex].duration_seconds || audio.duration || 0);
      if (shouldContinue && segmentIndex + 1 < config.segments.length) {
        var pause = predictionAfter(segmentIndex);
        if (pause) showPrediction(pause);
        else {
          var nextIndex = segmentIndex + 1;
          window.setTimeout(function () {
            if (!shouldContinue || segmentIndex !== nextIndex - 1) return;
            loadSegment(nextIndex);
            playCurrent();
          }, 350);
        }
      } else {
        shouldContinue = false;
        finished = true;
        setPlaying(false);
        progress.style.width = "100%";
        clearActive();
        status.textContent = "Conversation complete.";
      }
    });
    audio.addEventListener("error", function () { shouldContinue = false; setPlaying(false); status.textContent = "This audio part could not be loaded."; });
  });

  document.querySelectorAll("[data-recall-practice]").forEach(function (practice) {
    var revealButton = practice.querySelector("[data-recall-reveal]");
    var answer = practice.querySelector("[data-recall-answer]");
    if (!revealButton || !answer) return;
    revealButton.addEventListener("click", function () {
      var willReveal = answer.hidden;
      answer.hidden = !willReveal;
      revealButton.setAttribute("aria-expanded", String(willReveal));
      revealButton.textContent = willReveal ? "Hide the model follow-up" : "Reveal the model follow-up";
    });
  });
}());
