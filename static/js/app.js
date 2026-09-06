// htmx は既定で 4xx 応答を差し替えない（エラーページを描画しないための安全側の挙動）。
// ただし入力エラー（400）では、サーバーがエラー付きのフォームを返しているので、
// これを差し替えないと利用者が失敗理由を確認できない。
// 400 に限って差し替えを許可し、404 や 5xx は従来どおり差し替えない。
document.addEventListener("htmx:beforeSwap", function (event) {
  if (event.detail.xhr && event.detail.xhr.status === 400) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});
