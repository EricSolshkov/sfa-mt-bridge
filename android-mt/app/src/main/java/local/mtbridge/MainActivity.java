package local.mtbridge;

import android.app.*;
import android.os.*;
import android.content.*;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.util.AtomicFile;
import android.view.*;
import android.widget.*;
import com.chaquo.python.*;
import com.chaquo.python.android.AndroidPlatform;
import com.google.zxing.*;
import com.google.zxing.common.BitMatrix;
import com.google.zxing.qrcode.QRCodeWriter;
import com.google.zxing.qrcode.decoder.ErrorCorrectionLevel;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

@android.annotation.SuppressLint("SetTextI18n") // Personal Chinese-only utility; strings intentionally not localized.
public final class MainActivity extends Activity {
    private static final int INK = Color.rgb(25, 44, 53), TEAL = Color.rgb(0, 108, 103);
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private EditText path, name, rulesBase;
    private Switch root, keep;
    private Spinner resolve;
    private TextView status, detail, last, frameLabel;
    private Button check, convert, showLast, pause;
    private ProgressBar progress;
    private ImageView qr;
    private LinearLayout home, scan;
    private ScrollView scroll;
    private SharedPreferences prefs;
    private AtomicFile output;
    private JSONObject successful;
    private final Map<Integer, Bitmap> qrCache = new HashMap<>();
    private boolean busy, scanning, paused, foreground;
    private int frameIndex, interval = 300;
    private String diagnostic = "尚无诊断记录。";

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(TEAL);
        getWindow().setNavigationBarColor(Color.WHITE);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        prefs = getSharedPreferences("settings", MODE_PRIVATE);
        output = new AtomicFile(new File(getFilesDir(), "last-success.json"));
        buildUi();
        if (state != null) {
            path.setText(state.getString("path", path.getText().toString()));
            name.setText(state.getString("name", name.getText().toString()));
        }
        try (InputStream in = output.openRead()) {
            successful = new JSONObject(new String(SafeFiles.readLimited(in), StandardCharsets.UTF_8));
            updateLast();
        } catch (Exception ignored) { last.setText("还没有成功生成的配置"); }
    }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }
    private TextView text(String value, int size) {
        TextView view = new TextView(this); view.setText(value); view.setTextSize(size); view.setTextColor(INK);
        view.setPadding(0, dp(6), 0, dp(6)); return view;
    }
    private Button button(String value, LinearLayout parent, Runnable action) {
        Button button = new Button(this); button.setText(value); button.setAllCaps(false);
        button.setTextColor(TEAL); parent.addView(button, new LinearLayout.LayoutParams(-1, dp(52)));
        button.setOnClickListener(v -> action.run()); return button;
    }
    private LinearLayout card(LinearLayout parent) {
        LinearLayout view = new LinearLayout(this); view.setOrientation(LinearLayout.VERTICAL); view.setPadding(dp(18), dp(12), dp(18), dp(14));
        GradientDrawable bg = new GradientDrawable(); bg.setColor(Color.WHITE); bg.setCornerRadius(dp(18)); view.setBackground(bg);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2); lp.setMargins(0, dp(12), 0, 0); parent.addView(view, lp); return view;
    }
    private EditText field(String value, LinearLayout parent) {
        EditText edit = new EditText(this); edit.setText(value); edit.setTextSize(15); edit.setSingleLine(true);
        edit.setInputType(android.text.InputType.TYPE_CLASS_TEXT | android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        edit.setSelectAllOnFocus(false); parent.addView(edit, new LinearLayout.LayoutParams(-1, dp(52))); return edit;
    }
    private void buildUi() {
        LinearLayout outer = new LinearLayout(this); outer.setOrientation(LinearLayout.VERTICAL); outer.setBackgroundColor(Color.rgb(240, 246, 245));
        outer.setOnApplyWindowInsetsListener((v, insets) -> {
            v.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(), insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets;
        });
        scroll = new ScrollView(this); scroll.setFillViewport(true); outer.addView(scroll, new LinearLayout.LayoutParams(-1,-1));
        LinearLayout content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL); content.setPadding(dp(20),dp(16),dp(20),dp(24)); scroll.addView(content);
        home = new LinearLayout(this); home.setOrientation(LinearLayout.VERTICAL); content.addView(home);
        home.addView(text("MT 配置桥", 29));
        home.addView(text("在 Android 转换，在 iPhone 扫码导入", 15));
        LinearLayout source = card(home);
        source.addView(text("01  源配置", 18));
        source.addView(text("SFA config.json 完整路径", 13));
        path = field(prefs.getString("path", "/storage/emulated/0/Android/data/io.nekohasekai.sfa/files/config.json"), source);
        root = new Switch(this); root.setText("使用 Root 读取配置与规则"); root.setTextColor(INK); root.setChecked(prefs.getBoolean("root", false)); source.addView(root);
        source.addView(text("首次使用请在 Root 管理器中授权。只读取源文件。", 13));
        source.addView(text("规则基准目录（可选）", 13));
        rulesBase = field(prefs.getString("rulesBase", ""), source);
        rulesBase.setHint("留空：使用主配置所在目录");
        source.addView(text("配置与规则不在同一目录时，在这里填写相对规则路径的起点。例如路径是 RuleProviders/{tag}.json，应填写 RuleProviders 的上一级目录。绝对规则路径不受影响。", 12));
        check = button("检查文件访问", source, () -> runConversion(true));
        LinearLayout options = card(home);
        options.addView(text("02  导出设置", 18));
        name = field(prefs.getString("name", "SFA → MT"), options);
        options.addView(text("match_only 的迁移方式", 13));
        resolve = new Spinner(this);
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item,
            new String[]{"普通 resolve（保留 IP 分流兜底）", "移除 resolve（改变 IP 分流兜底）"});
        resolve.setAdapter(adapter); resolve.setSelection(prefs.getInt("resolve", 0)); options.addView(resolve);
        options.addView(text("普通 resolve 可能影响后续连接使用的 IP；两种方式都不是 match_only 的无损替代。", 12));
        keep = new Switch(this); keep.setText("保留非 TUN 入站与本地 API"); keep.setTextColor(INK); keep.setChecked(prefs.getBoolean("keep", false)); options.addView(keep);
        convert = button("更新并生成二维码", options, () -> runConversion(false));
        convert.setTextColor(Color.WHITE); convert.setBackgroundTintList(android.content.res.ColorStateList.valueOf(TEAL));
        LinearLayout result = card(home);
        status = text("准备就绪", 18); result.addView(status);
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal); progress.setIndeterminate(true); progress.setVisibility(View.GONE); result.addView(progress);
        detail = text("先检查文件访问，再更新订阅并转换。", 13); detail.setTextIsSelectable(true); result.addView(detail);
        last = text("还没有成功生成的配置", 13); result.addView(last);
        showLast = button("显示上次成功的二维码", result, this::showQr); showLast.setEnabled(false);
        button("复制诊断信息", result, () -> {
            ((ClipboardManager)getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(ClipData.newPlainText("MT 配置桥诊断", diagnostic));
            Toast.makeText(this, "已复制诊断信息（不含订阅正文）", Toast.LENGTH_SHORT).show();
        });
        // Daily actions stay at the top; path and migration settings persist below.
        options.removeView(convert); result.addView(convert, 0);
        home.removeView(result); home.addView(result, 2);
        home.addView(text("转换在本机完成，仅向配置中的订阅源请求数据。生成结果保存在应用内；更新失败保留上次结果。", 12));
        button("组件与开源许可", home, this::showLicenses);

        scan = new LinearLayout(this); scan.setOrientation(LinearLayout.VERTICAL); scan.setVisibility(View.GONE); content.addView(scan);
        scan.addView(text("用 iPhone 扫描", 27));
        scan.addView(text("MT → 新建配置 → 扫描二维码\n保持对准，直到 MT 提示导入。", 16));
        qr = new ImageView(this); qr.setBackgroundColor(Color.WHITE); qr.setAdjustViewBounds(true); qr.setScaleType(ImageView.ScaleType.FIT_CENTER);
        scan.addView(qr, new LinearLayout.LayoutParams(-1, -2));
        frameLabel = text("正在准备二维码…", 14); scan.addView(frameLabel);
        scan.addView(text("二维码循环播放，漏掉的帧可在下一轮补齐。屏幕上的帧数不是 iPhone 的接收进度。", 13));
        pause = button("暂停", scan, () -> { paused = !paused; pause.setText(paused ? "继续播放" : "暂停"); if (!paused) animate(); });
        button("切换播放速度", scan, () -> { interval = interval == 300 ? 600 : 300; Toast.makeText(this, interval == 600 ? "慢速：每秒约 1.7 帧" : "标准：每秒约 3.3 帧", Toast.LENGTH_SHORT).show(); });
        scan.addView(text("这是完整配置快照。以后更新需要重新扫码；同名配置是否覆盖以 MT 的提示为准。", 13));
        button("返回设置", scan, this::hideQr);
        setContentView(outer);
    }
    private void saveSettings() {
        prefs.edit().putString("path", path.getText().toString().trim()).putString("name", name.getText().toString().trim())
            .putString("rulesBase", rulesBase.getText().toString().trim())
            .putBoolean("root", root.isChecked()).putBoolean("keep", keep.isChecked()).putInt("resolve", resolve.getSelectedItemPosition()).apply();
    }
    private void setBusy(boolean value) {
        busy = value; check.setEnabled(!value); convert.setEnabled(!value); path.setEnabled(!value); name.setEnabled(!value);
        root.setEnabled(!value); keep.setEnabled(!value); resolve.setEnabled(!value); showLast.setEnabled(!value && successful != null);
        rulesBase.setEnabled(!value);
        progress.setVisibility(value ? View.VISIBLE : View.GONE);
    }
    private void runConversion(boolean checkOnly) {
        if (busy) return;
        saveSettings(); setBusy(true); status.setText(checkOnly ? "检查文件访问" : "正在转换"); detail.setText("初始化转换器…");
        scroll.post(() -> scroll.smoothScrollTo(0,0));
        String source = path.getText().toString().trim(), profile = name.getText().toString().trim();
        String base = rulesBase.getText().toString().trim();
        String mode = resolve.getSelectedItemPosition() == 0 ? "ordinary" : "remove";
        boolean useRoot = root.isChecked(), keepServices = keep.isChecked();
        worker.execute(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                NativeBridge bridge = new NativeBridge(useRoot, message -> runOnUiThread(() -> { if (!isDestroyed()) detail.setText(message); }));
                String returned = Python.getInstance().getModule("mobile_bridge").callAttr("run", bridge, source, profile, mode, keepServices, checkOnly, base).toString();
                JSONObject data = new JSONObject(returned);
                if (data.optBoolean("ok") && !checkOnly) {
                    // Do not publish until both conversion and QR image generation work.
                    QRCodeWriter writer = new QRCodeWriter();
                    JSONArray frames = data.getJSONArray("frames");
                    for (int i = 0; i < frames.length(); i++) writer.encode(frames.getString(i), BarcodeFormat.QR_CODE, 1, 1, qrHints());
                    FileOutputStream stream = null;
                    try { stream = output.startWrite(); stream.write(returned.getBytes(StandardCharsets.UTF_8)); output.finishWrite(stream); }
                    catch (Exception e) { if (stream != null) output.failWrite(stream); throw e; }
                }
                runOnUiThread(() -> { if (!isDestroyed()) finishConversion(data, checkOnly); });
            } catch (Exception error) {
                runOnUiThread(() -> {
                    if (isDestroyed()) return;
                    setBusy(false); status.setText("操作未完成，旧结果保留");
                    diagnostic = "MT 配置桥 0.1.2\n运行环境或结果保存失败\n类型：" + error.getClass().getSimpleName();
                    detail.setText(diagnostic + "\n请检查可用存储空间；必要时将诊断信息反馈给开发者。");
                });
            }
        });
    }
    private void finishConversion(JSONObject data, boolean checkOnly) {
        setBusy(false);
        if (!data.optBoolean("ok")) {
            String code = data.optString("code");
            status.setText("未完成，旧结果保留");
            diagnostic = "MT 配置桥 0.1.2\nAndroid " + Build.VERSION.RELEASE + " / API " + Build.VERSION.SDK_INT +
                "\n读取模式：" + (root.isChecked() ? "Root" : "普通") +
                "\n阶段：" + data.optString("stage") + "\n代码：" + code + "\n" + data.optString("message") + "\n" + data.optString("trace");
            detail.setText(explain(code) + "\n\n" + diagnostic); return;
        }
        if (checkOnly) { status.setText("文件访问检查通过"); detail.setText(data.optString("message")); diagnostic = "MT 配置桥 0.1.2\n文件访问检查通过；未下载订阅。"; return; }
        successful = data; qrCache.clear(); updateLast(); showLast.setEnabled(true);
        status.setText("转换成功");
        detail.setText(data.optInt("nodes") + " 个节点 · " + data.optInt("groups") + " 个分组\n完整 Schema、引用和循环校验通过。");
        diagnostic = "MT 配置桥 0.1.2\n转换成功\n节点：" + data.optInt("nodes") + "\n分组：" + data.optInt("groups") + "\n" + data.optString("generated_at");
        showQr();
    }
    private String explain(String code) {
        if (code.contains("SU_UNAVAILABLE")) return "未找到 su。请确认手机已 Root，且此应用可调用 su。";
        if (code.contains("ROOT_TIMEOUT")) return "Root 授权或读取超时。请在 Root 管理器中检查授权后重试。";
        if (code.contains("ROOT_DENIED")) return "Root 未获授权，或 Root 环境仍无法读取该文件。请检查授权及目录权限。";
        if (code.contains("FILE_UNAVAILABLE") || code.contains("PERMISSION_OR_PATH")) return "找不到文件或没有读取权限。请检查完整路径，受保护的 SFA 目录需要开启 Root。";
        if (code.contains("HTTP")) return "订阅服务器返回错误；检查订阅是否有效。未替换上次结果。";
        if (code.contains("TLS")) return "订阅 TLS 校验失败。请检查设备时间和服务器证书。";
        if (code.contains("NETWORK") || code.contains("DNS")) return "下载订阅失败。请检查手机网络和订阅域名；可稍后重试。";
        if (code.contains("TOO_LARGE")) return "文件或订阅超过 20 MiB 上限。";
        return "请根据失败阶段检查源配置和规则；可复制下方诊断信息。";
    }
    private void updateLast() {
        String generated = successful.optString("generated_at");
        try { generated = java.time.Instant.parse(generated).atZone(java.time.ZoneId.systemDefault()).format(java.time.format.DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")); }
        catch (Exception ignored) {}
        last.setText("上次成功：" + successful.optString("name") + "\n" + generated +
            "\n" + successful.optInt("nodes") + " 个节点 · " + successful.optInt("groups") + " 个分组");
        showLast.setEnabled(!busy);
    }
    private Map<EncodeHintType,Object> qrHints() {
        Map<EncodeHintType,Object> hints = new EnumMap<>(EncodeHintType.class);
        hints.put(EncodeHintType.ERROR_CORRECTION, ErrorCorrectionLevel.L); hints.put(EncodeHintType.MARGIN, 4); return hints;
    }
    private Bitmap renderQr(String payload) throws WriterException {
        BitMatrix matrix = new QRCodeWriter().encode(payload, BarcodeFormat.QR_CODE, 800, 800, qrHints());
        int w = matrix.getWidth(), h = matrix.getHeight(); int[] pixels = new int[w*h];
        for (int y=0;y<h;y++) for (int x=0;x<w;x++) pixels[y*w+x] = matrix.get(x,y) ? Color.BLACK : Color.WHITE;
        return Bitmap.createBitmap(pixels,w,h,Bitmap.Config.ARGB_8888);
    }
    private void showQr() {
        if (successful == null || busy) return;
        scanning = true; paused = false; frameIndex = 0; pause.setText("暂停"); home.setVisibility(View.GONE); scan.setVisibility(View.VISIBLE);
        scroll.post(() -> scroll.scrollTo(0,0));
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        WindowManager.LayoutParams attrs = getWindow().getAttributes(); attrs.screenBrightness = 0.9f; getWindow().setAttributes(attrs);
        animate();
    }
    private final Runnable tick = this::animate;
    private void animate() {
        handler.removeCallbacks(tick);
        if (!scanning || paused || !foreground || successful == null) return;
        try {
            JSONArray frames = successful.getJSONArray("frames"); int index = frameIndex % frames.length();
            Bitmap bitmap = qrCache.get(index);
            if (bitmap == null) {
                bitmap = renderQr(frames.getString(index));
                // Bound bitmap cache, regardless of profile size.
                if (qrCache.size() >= 6) qrCache.clear();
                qrCache.put(index, bitmap);
            }
            qr.setImageBitmap(bitmap);
            if (qr.getDrawable() instanceof android.graphics.drawable.BitmapDrawable)
                ((android.graphics.drawable.BitmapDrawable) qr.getDrawable()).setFilterBitmap(false);
            frameLabel.setText(successful.optString("name") + "  ·  帧 " + (index+1) + " / " + frames.length() + "  ·  循环播放");
            frameIndex = index + 1; handler.postDelayed(tick, interval);
        } catch (Exception e) { paused = true; pause.setText("重试播放"); frameLabel.setText("二维码渲染失败，请返回后重试。"); }
    }
    private void hideQr() {
        scanning = false; handler.removeCallbacks(tick); scan.setVisibility(View.GONE); home.setVisibility(View.VISIBLE);
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        WindowManager.LayoutParams attrs = getWindow().getAttributes(); attrs.screenBrightness = -1; getWindow().setAttributes(attrs);
    }
    private void showLicenses() {
        String value;
        try (InputStream in = getAssets().open("NOTICE.txt")) { value = new String(SafeFiles.readLimited(in), StandardCharsets.UTF_8); }
        catch (Exception e) { value = "见工程 THIRD_PARTY_NOTICES.md 与随附许可证。"; }
        TextView text = text(value, 13); text.setPadding(dp(18),dp(8),dp(18),dp(8)); text.setTextIsSelectable(true);
        ScrollView scroll = new ScrollView(this); scroll.addView(text);
        new AlertDialog.Builder(this).setTitle("开源组件").setView(scroll).setPositiveButton("关闭", null).show();
    }
    @Override protected void onStart() { super.onStart(); foreground = true; if (scanning && !paused) animate(); }
    @Override protected void onStop() { foreground = false; handler.removeCallbacks(tick); super.onStop(); }
    @Override protected void onSaveInstanceState(Bundle state) { saveSettings(); state.putString("path",path.getText().toString()); state.putString("name",name.getText().toString()); super.onSaveInstanceState(state); }
    @Override public void onBackPressed() { if (scanning) hideQr(); else super.onBackPressed(); }
    @Override protected void onDestroy() { handler.removeCallbacksAndMessages(null); worker.shutdownNow(); super.onDestroy(); }
}
