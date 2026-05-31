// SrednaBG framing playground — wires controls to a single render() call.
// Change SHOT below to preview a different raw PNG pair from ../android/.

const SHOT = "02-android";
const RAW_PATHS = {
  light: `../android/${SHOT}-light-bg.png`,
  dark:  `../android/${SHOT}-dark-bg.png`,
};

const frame    = document.getElementById("frame");
const title    = document.getElementById("title");
const phone    = document.getElementById("phone");
const bgPicker = document.getElementById("bgPicker");
const bgHex    = document.getElementById("bgHex");
const fontSel  = document.getElementById("font");
const tSize    = document.getElementById("titleSize");
const tSizeOut = document.getElementById("titleSizeOut");
const tText    = document.getElementById("titleText");

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

function currentTheme() {
  return document.querySelector('input[name="theme"]:checked').value;
}

function render() {
  phone.src = RAW_PATHS[currentTheme()];
  frame.style.background = bgHex.value;
  title.style.fontFamily = `"${fontSel.value}", system-ui, sans-serif`;
  title.style.fontSize = `${tSize.value}px`;
  title.textContent = tText.value;
  tSizeOut.value = `${tSize.value} px`;
}

// Brand-color swatches: set both inputs in sync, then re-render.
document.querySelectorAll(".swatches button").forEach((b) => {
  b.addEventListener("click", () => {
    const c = b.dataset.color;
    bgHex.value = c;
    bgPicker.value = c;
    render();
  });
});

// Color picker → hex field, always.
bgPicker.addEventListener("input", () => {
  bgHex.value = bgPicker.value.toUpperCase();
  render();
});

// Hex field → picker, only when the value is a valid #RRGGBB.
bgHex.addEventListener("input", () => {
  if (HEX_RE.test(bgHex.value)) {
    bgPicker.value = bgHex.value;
    render();
  }
});

// Theme radios + font dropdown + size slider + title textarea.
document.querySelectorAll('input[name="theme"], #font, #titleSize, #titleText')
  .forEach((el) => {
    el.addEventListener("input", render);
    el.addEventListener("change", render);
  });

render();
