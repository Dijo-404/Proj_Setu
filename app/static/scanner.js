const script = document.currentScript;
const form = document.getElementById("scan-form");
const input = document.getElementById("serial-input");
const alertBox = document.getElementById("scan-alert");
const cameraButton = document.getElementById("camera-button");
const video = document.getElementById("scanner-video");

let detector = null;
let stream = null;
let scanning = false;
let lastCode = "";

function showAlert(message, kind = "error") {
  if (!alertBox) return;
  alertBox.textContent = message;
  alertBox.className = `alert ${kind}`;
}

async function submitSerial(serial) {
  if (!serial) return;
  const data = new FormData();
  data.append("serial_number", serial);
  const response = await fetch(form.action, { method: "POST", body: data });
  const payload = await response.json();
  if (!payload.ok) {
    showAlert(payload.error || "Scan rejected", "error");
    return;
  }
  window.location.reload();
}

async function scanLoop() {
  if (!scanning || !detector || !video) return;
  try {
    const codes = await detector.detect(video);
    if (codes.length > 0) {
      const code = codes[0].rawValue.trim();
      if (code && code !== lastCode) {
        lastCode = code;
        await submitSerial(code);
        return;
      }
    }
  } catch (error) {
    showAlert("Camera scan failed", "error");
  }
  requestAnimationFrame(scanLoop);
}

async function startCamera() {
  if (!("BarcodeDetector" in window)) {
    showAlert("Camera scanner is not available in this browser", "warn");
    input.focus();
    return;
  }
  detector = new BarcodeDetector({ formats: ["code_128"] });
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
  } catch (error) {
    showAlert("Camera permission denied or unavailable", "error");
    return;
  }
  video.srcObject = stream;
  await video.play();
  scanning = true;
  showAlert("Camera active", "");
  requestAnimationFrame(scanLoop);
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitSerial(input.value.trim());
  });
}

if (cameraButton) {
  cameraButton.addEventListener("click", startCamera);
}

window.addEventListener("beforeunload", () => {
  if (stream) {
    stream.getTracks().forEach((track) => track.stop());
  }
});
