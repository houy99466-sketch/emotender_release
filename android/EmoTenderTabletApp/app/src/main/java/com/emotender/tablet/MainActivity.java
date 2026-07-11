package com.emotender.tablet;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.ContentValues;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.speech.RecognizerIntent;
import android.text.InputType;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.ArrayList;

public class MainActivity extends Activity {
    private static final int REQUEST_SPEECH = 1001;
    private static final int REQUEST_WRITE_IMAGE = 1002;

    private WebView webView;
    private SharedPreferences prefs;
    private boolean errorDialogShown;
    private String pendingImageDataUrl;
    private String pendingImageFileName;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        prefs = getSharedPreferences("emotender", MODE_PRIVATE);

        webView = new WebView(this);
        configureWebView();
        setContentView(webView);
        showLocalConfigPage();
        showBackendDialog();
    }

    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        webView.addJavascriptInterface(new AndroidBridge(), "EmoTenderAndroid");
        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request != null && request.isForMainFrame() && !errorDialogShown) {
                    errorDialogShown = true;
                    runOnUiThread(() -> showBackendDialog());
                }
            }
        });

        webView.setOnLongClickListener(view -> {
            showBackendDialog();
            return true;
        });
    }

    private void loadBackendPage() {
        errorDialogShown = false;
        String url = prefs.getString("backend_url", "").trim();
        if (url.isEmpty()) {
            showLocalConfigPage();
            showBackendDialog();
            return;
        }
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "http://" + url;
        }
        if (!url.endsWith("/")) {
            url = url + "/";
        }
        prefs.edit().putString("backend_url", url.substring(0, url.length() - 1)).apply();
        webView.loadUrl(url);
    }

    private void showLocalConfigPage() {
        String html = "<!doctype html><html><head><meta charset='utf-8'>"
                + "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                + "<style>"
                + "html,body{margin:0;height:100%;background:#050708;color:#c8d6dc;"
                + "font-family:monospace;display:flex;align-items:center;justify-content:center;}"
                + ".box{width:min(86vw,420px);text-align:center;line-height:1.8;}"
                + "h1{font-size:22px;color:#8cc8e0;font-weight:400;letter-spacing:.08em;}"
                + "button{margin-top:18px;padding:10px 28px;background:#081014;color:#8cc8e0;"
                + "border:1px solid rgba(140,200,224,.45);font-family:monospace;font-size:14px;}"
                + "</style></head><body><div class='box'>"
                + "<h1>EmoTender</h1>"
                + "<p>请输入 Windows 后端地址后进入系统。</p>"
                + "<p>例如：http://192.168.43.252:8000</p>"
                + "<button onclick='EmoTenderAndroid.configureBackend()'>设置后端地址</button>"
                + "</div></body></html>";
        webView.loadDataWithBaseURL("https://emotender.local/", html, "text/html", "UTF-8", null);
    }

    private void showBackendDialog() {
        EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_TEXT_VARIATION_URI);
        input.setHint("http://电脑IP:8000");
        input.setText(prefs.getString("backend_url", ""));
        input.setSelectAllOnFocus(true);

        new AlertDialog.Builder(this)
                .setTitle("EmoTender Backend")
                .setMessage("输入 Windows 后端地址，例如 http://192.168.43.252:8000。")
                .setView(input)
                .setPositiveButton("Load", (dialog, which) -> {
                    String value = input.getText().toString().trim();
                    if (!value.isEmpty()) {
                        prefs.edit().putString("backend_url", value).apply();
                        loadBackendPage();
                    }
                })
                .setNegativeButton("Cancel", (dialog, which) -> showLocalConfigPage())
                .show();
    }

    private void startSpeechRecognition() {
        evaluate("window.onAndroidSpeechStatus && window.onAndroidSpeechStatus('LISTENING')");
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN");
        intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "请说出你现在的状态");
        intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
        try {
            startActivityForResult(intent, REQUEST_SPEECH);
        } catch (Exception exc) {
            evaluate("window.onAndroidSpeechStatus && window.onAndroidSpeechStatus('IDLE');"
                    + "window.R && window.R('这台设备没有可用的系统语音识别。请手动输入文字后点 Send。')");
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_SPEECH) {
            return;
        }

        if (resultCode == RESULT_OK && data != null) {
            ArrayList<String> matches = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
            String text = matches != null && !matches.isEmpty() ? matches.get(0).trim() : "";
            if (!text.isEmpty()) {
                evaluate("window.submitRecognizedText && window.submitRecognizedText("
                        + JSONObject.quote(text)
                        + ")");
            } else {
                evaluate("window.onAndroidSpeechStatus && window.onAndroidSpeechStatus('IDLE');"
                        + "window.R && window.R('我没太听清，能再说一遍吗？')");
            }
        } else {
            evaluate("window.onAndroidSpeechStatus && window.onAndroidSpeechStatus('IDLE')");
        }
    }

    private void evaluate(String script) {
        if (webView == null) {
            return;
        }
        webView.post(() -> webView.evaluateJavascript(script, null));
    }

    private void requestImageSave(String dataUrl, String fileName) {
        pendingImageDataUrl = dataUrl;
        pendingImageFileName = sanitizeFileName(fileName);
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q
                && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(
                    new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE},
                    REQUEST_WRITE_IMAGE
            );
            return;
        }
        saveImageToGallery(pendingImageDataUrl, pendingImageFileName);
    }

    private String sanitizeFileName(String fileName) {
        String cleaned = fileName == null ? "" : fileName.replaceAll("[^a-zA-Z0-9._-]", "_");
        if (cleaned.isEmpty()) {
            cleaned = "EmoTender-result.png";
        }
        if (!cleaned.toLowerCase().endsWith(".png")) {
            cleaned = cleaned + ".png";
        }
        return cleaned;
    }

    private byte[] decodePngDataUrl(String dataUrl) {
        if (dataUrl == null) {
            throw new IllegalArgumentException("image_data_missing");
        }
        int comma = dataUrl.indexOf(',');
        if (comma < 0 || comma == dataUrl.length() - 1) {
            throw new IllegalArgumentException("image_data_invalid");
        }
        return Base64.decode(dataUrl.substring(comma + 1), Base64.DEFAULT);
    }

    private void saveImageToGallery(String dataUrl, String fileName) {
        new Thread(() -> {
            Uri insertedUri = null;
            try {
                byte[] imageBytes = decodePngDataUrl(dataUrl);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    ContentValues values = new ContentValues();
                    values.put(MediaStore.Images.Media.DISPLAY_NAME, fileName);
                    values.put(MediaStore.Images.Media.MIME_TYPE, "image/png");
                    values.put(
                            MediaStore.Images.Media.RELATIVE_PATH,
                            Environment.DIRECTORY_PICTURES + "/EmoTender"
                    );
                    values.put(MediaStore.Images.Media.IS_PENDING, 1);
                    insertedUri = getContentResolver().insert(
                            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                            values
                    );
                    if (insertedUri == null) {
                        throw new IOException("media_store_insert_failed");
                    }
                    try (OutputStream output = getContentResolver().openOutputStream(insertedUri)) {
                        if (output == null) {
                            throw new IOException("media_store_output_failed");
                        }
                        output.write(imageBytes);
                    }
                    values.clear();
                    values.put(MediaStore.Images.Media.IS_PENDING, 0);
                    getContentResolver().update(insertedUri, values, null, null);
                } else {
                    File pictureRoot = Environment.getExternalStoragePublicDirectory(
                            Environment.DIRECTORY_PICTURES
                    );
                    File outputDir = new File(pictureRoot, "EmoTender");
                    if (!outputDir.exists() && !outputDir.mkdirs()) {
                        throw new IOException("picture_directory_failed");
                    }
                    File outputFile = new File(outputDir, fileName);
                    try (OutputStream output = new FileOutputStream(outputFile)) {
                        output.write(imageBytes);
                    }
                    MediaScannerConnection.scanFile(
                            this,
                            new String[]{outputFile.getAbsolutePath()},
                            new String[]{"image/png"},
                            null
                    );
                }
                runOnUiThread(() -> Toast.makeText(
                        this,
                        "图片已保存到 Pictures/EmoTender",
                        Toast.LENGTH_LONG
                ).show());
            } catch (Exception exc) {
                if (insertedUri != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    getContentResolver().delete(insertedUri, null, null);
                }
                runOnUiThread(() -> Toast.makeText(
                        this,
                        "图片保存失败：" + exc.getMessage(),
                        Toast.LENGTH_LONG
                ).show());
            }
        }).start();
    }

    @Override
    public void onRequestPermissionsResult(
            int requestCode,
            String[] permissions,
            int[] grantResults
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode != REQUEST_WRITE_IMAGE) {
            return;
        }
        if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            saveImageToGallery(pendingImageDataUrl, pendingImageFileName);
        } else {
            Toast.makeText(this, "没有存储权限，无法保存图片。", Toast.LENGTH_LONG).show();
        }
    }

    public class AndroidBridge {
        @JavascriptInterface
        public void startSpeech() {
            runOnUiThread(() -> startSpeechRecognition());
        }

        @JavascriptInterface
        public void configureBackend() {
            runOnUiThread(() -> showBackendDialog());
        }

        @JavascriptInterface
        public void saveImage(String dataUrl, String fileName) {
            runOnUiThread(() -> requestImageSave(dataUrl, fileName));
        }
    }
}
