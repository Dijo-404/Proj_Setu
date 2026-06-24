const script = document.currentScript;
const form = document.getElementById("scan-form");
const input = document.getElementById("serial-input");
const sourceInput = document.getElementById("scan-source");
const alertBox = document.getElementById("scan-alert");
const cameraButton = document.getElementById("camera-button");
const photoInput = document.getElementById("photo-scan-input");
const video = document.getElementById("scanner-video");

const canManual = form && form.dataset.canManual === "true";

let nativeDetector = null;
let zxingReader = null;
let nativeStream = null;
let scanning = false;
let lastCode = "";
let submitting = false;

function showAlert(message, kind = "error") {
  if (!alertBox) return;
  if (!message) {
    alertBox.textContent = "";
    alertBox.className = "alert hidden";
    return;
  }
  alertBox.textContent = message;
  alertBox.className = kind ? `alert ${kind}` : "alert";
}

function resultText(result) {
  if (!result) return "";
  if (typeof result.getText === "function") return result.getText().trim();
  return String(result.text || result.rawValue || "").trim();
}

function createZxingReader() {
  if (!window.ZXing || !window.ZXing.BrowserMultiFormatReader) return null;
  const hints = new Map();
  if (window.ZXing.DecodeHintType && window.ZXing.BarcodeFormat) {
    hints.set(window.ZXing.DecodeHintType.POSSIBLE_FORMATS, [window.ZXing.BarcodeFormat.CODE_128]);
    hints.set(window.ZXing.DecodeHintType.TRY_HARDER, true);
  }
  return new window.ZXing.BrowserMultiFormatReader(hints, 250);
}

function stopCamera() {
  scanning = false;
  if (zxingReader) {
    if (typeof zxingReader.stopContinuousDecode === "function") zxingReader.stopContinuousDecode();
    if (typeof zxingReader.reset === "function") zxingReader.reset();
    zxingReader = null;
  }
  if (nativeStream) {
    nativeStream.getTracks().forEach((track) => track.stop());
    nativeStream = null;
  }
  if (video) video.srcObject = null;
}

async function submitSerial(serial, source = "camera") {
  if (!serial || submitting || !form) return;
  submitting = true;
  if (input) input.value = serial;
  if (sourceInput) sourceInput.value = source;
  const data = new FormData();
  data.append("serial_number", serial);
  data.append("scan_source", source);
  try {
    const response = await fetch(form.action, { method: "POST", body: data, headers: { Accept: "application/json" } });
    const payload = await response.json();
    if (!payload.ok) {
      showAlert(payload.error || "Scan rejected", "error");
      submitting = false;
      return;
    }
    stopCamera();
    window.location.reload();
  } catch (error) {
    showAlert("Scan could not be saved. Check the connection and try again.", "error");
    submitting = false;
  }
}

async function createNativeDetector() {
  if (!("BarcodeDetector" in window)) return null;
  try {
    if (typeof BarcodeDetector.getSupportedFormats === "function") {
      const formats = await BarcodeDetector.getSupportedFormats();
      if (formats.length && !formats.includes("code_128")) return null;
    }
    return new BarcodeDetector({ formats: ["code_128"] });
  } catch (error) {
    return null;
  }
}

async function nativeScanLoop() {
  if (!scanning || !nativeDetector || !video || submitting) return;
  try {
    const codes = await nativeDetector.detect(video);
    const code = resultText(codes[0]);
    if (code && code !== lastCode) {
      lastCode = code;
      await submitSerial(code, "camera");
      return;
    }
  } catch (error) {
    showAlert("Camera scan failed. Try photo capture.", "warn");
  }
  requestAnimationFrame(nativeScanLoop);
}

async function startZxingCamera() {
  zxingReader = createZxingReader();
  if (!zxingReader || !video) return false;
  await zxingReader.decodeFromConstraints(
    {
      audio: false,
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
    },
    video,
    (result) => {
      const code = resultText(result);
      if (!code || code === lastCode || submitting) return;
      lastCode = code;
      submitSerial(code, "camera");
    }
  );
  showAlert("Camera active", "");
  return true;
}

async function startNativeCamera() {
  nativeDetector = await createNativeDetector();
  if (!nativeDetector || !video) return false;
  nativeStream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: {
      facingMode: { ideal: "environment" },
      width: { ideal: 1280 },
      height: { ideal: 720 },
    },
  });
  video.srcObject = nativeStream;
  await video.play();
  scanning = true;
  showAlert("Camera active", "");
  requestAnimationFrame(nativeScanLoop);
  return true;
}

async function startCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.isSecureContext) {
    showAlert("Live camera needs HTTPS or localhost. Use Take photo here, or open Setu with HTTPS.", "warn");
    return;
  }
  stopCamera();
  if (cameraButton) {
    cameraButton.disabled = true;
    cameraButton.textContent = "Starting";
  }
  try {
    if (await startZxingCamera()) {
      if (cameraButton) cameraButton.textContent = "Camera active";
      return;
    }
    if (await startNativeCamera()) {
      if (cameraButton) cameraButton.textContent = "Camera active";
      return;
    }
    showAlert("Camera scanner is not available in this browser. Use Take photo.", "warn");
  } catch (error) {
    stopCamera();
    showAlert("Camera permission denied or unavailable. Use Take photo.", "error");
    if (cameraButton) {
      cameraButton.disabled = false;
      cameraButton.textContent = "Camera";
    }
  }
}

async function decodePhotoWithZxing(url) {
  const reader = createZxingReader();
  if (!reader) return "";
  try {
    return resultText(await reader.decodeFromImageUrl(url));
  } finally {
    if (typeof reader.reset === "function") reader.reset();
  }
}

async function decodePhotoWithNative(url) {
  const detector = await createNativeDetector();
  if (!detector) return "";
  const image = new Image();
  const loaded = new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = reject;
  });
  image.src = url;
  if (typeof image.decode === "function") {
    await image.decode();
  } else {
    await loaded;
  }
  const codes = await detector.detect(image);
  return resultText(codes[0]);
}

async function decodePhoto(file) {
  if (!file) return;
  showAlert("Reading barcode photo", "");
  const url = URL.createObjectURL(file);
  try {
    const code = (await decodePhotoWithZxing(url)) || (await decodePhotoWithNative(url));
    if (!code) {
      showAlert("No Code128 barcode found in the photo", "warn");
      return;
    }
    await submitSerial(code, "camera");
  } catch (error) {
    showAlert("Could not read the barcode photo", "error");
  } finally {
    URL.revokeObjectURL(url);
    if (photoInput) photoInput.value = "";
  }
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!canManual) {
      showAlert("Use camera scan to add serials", "warn");
      return;
    }
    await submitSerial(input.value.trim(), "manual");
  });
}

if (cameraButton) {
  cameraButton.addEventListener("click", startCamera);
}

if (photoInput) {
  photoInput.addEventListener("change", () => {
    decodePhoto(photoInput.files && photoInput.files[0]);
  });
}

window.addEventListener("beforeunload", () => {
  stopCamera();
});
