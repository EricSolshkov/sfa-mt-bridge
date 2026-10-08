package local.mtbridge;

import android.content.Context;
import android.util.Base64;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import com.google.zxing.*;
import com.google.zxing.common.*;
import com.google.zxing.qrcode.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import org.json.*;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class EmbeddedConverterTest {
    public static class FixtureBridge {
        public void progress(String text) {}
        public String readBase64(String path) throws IOException {
            return Base64.encodeToString(SafeFiles.read(path,false),Base64.NO_WRAP);
        }
        public String fetchBase64(String url,String ua) {
            String nodes = "{\"outbounds\":[{\"type\":\"shadowsocks\",\"tag\":\"测试 🇯🇵\",\"server\":\"192.0.2.1\",\"server_port\":443,\"method\":\"chacha20-ietf-poly1305\",\"password\":\"synthetic-only\"}]}";
            return Base64.encodeToString(nodes.getBytes(StandardCharsets.UTF_8),Base64.NO_WRAP);
        }
    }

    @Test public void bundledPythonSchemaConversionAndQrRoundTrip() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        File source = new File(context.getFilesDir(),"synthetic-source.json");
        String config = "{\"inbounds\":[{\"type\":\"tun\",\"tag\":\"tun\",\"address\":[\"172.19.0.1/24\"],\"auto_route\":true}],\"outbounds\":[{\"type\":\"direct\",\"tag\":\"Direct\"},{\"type\":\"selector\",\"tag\":\"Proxy\",\"providers\":[\"P\"]}],\"outbound_providers\":[{\"type\":\"remote\",\"tag\":\"P\",\"url\":\"https://example.invalid/test\"}],\"route\":{\"final\":\"Proxy\"}}";
        try (FileOutputStream out = new FileOutputStream(source)) { out.write(config.getBytes(StandardCharsets.UTF_8)); }
        String raw = Python.getInstance().getModule("mobile_bridge").callAttr("run",new FixtureBridge(),source.getAbsolutePath(),"离线自检 🇯🇵","ordinary",false,false).toString();
        JSONObject result = new JSONObject(raw);
        assertTrue(result.toString(),result.getBoolean("ok"));
        assertEquals(1,result.getInt("nodes"));
        assertEquals(1,result.getInt("groups"));
        JSONArray frames = result.getJSONArray("frames");
        for (int i=0;i<frames.length();i++) {
            String payload = frames.getString(i);
            BitMatrix matrix = new QRCodeWriter().encode(payload,BarcodeFormat.QR_CODE,800,800);
            int[] pixels = new int[800*800];
            for (int y=0;y<800;y++) for (int x=0;x<800;x++) pixels[y*800+x]=matrix.get(x,y)?0xff000000:0xffffffff;
            Result decoded = new QRCodeReader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(800,800,pixels))));
            assertEquals(payload,decoded.getText());
        }
        // Seed only this emulator/test installation for native UI verification.
        try (FileOutputStream out = new FileOutputStream(new File(context.getFilesDir(),"last-success.json"))) { out.write(raw.getBytes(StandardCharsets.UTF_8)); }
        String checked = Python.getInstance().getModule("mobile_bridge").callAttr("run",new FixtureBridge(),source.getAbsolutePath(),"自检","ordinary",false,true).toString();
        assertTrue(new JSONObject(checked).getBoolean("checked"));
        NativeBridge nativeBridge = new NativeBridge(false, message -> {});
        try { nativeBridge.fetchBase64("http://example.invalid/plaintext","test"); fail(); }
        catch (IOException expected) { assertEquals("MTB_HTTPS_REQUIRED",expected.getMessage()); }
        String failure = Python.getInstance().getModule("mobile_bridge").callAttr("run", nativeBridge, "/missing/config.json","自检","ordinary",false,true).toString();
        JSONObject error = new JSONObject(failure);
        assertFalse(error.getBoolean("ok"));
        assertEquals("MTB_FILE_UNAVAILABLE",error.getString("code"));
    }
}
