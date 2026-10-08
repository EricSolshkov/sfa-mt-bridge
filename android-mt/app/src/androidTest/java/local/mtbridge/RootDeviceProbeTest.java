package local.mtbridge;

import android.os.Bundle;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.junit.Test;
import org.junit.runner.RunWith;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;
import static org.junit.Assert.*;

/** Explicitly invoked, read-only physical-device diagnosis. Never reads file content. */
@RunWith(AndroidJUnit4.class)
public class RootDeviceProbeTest {
    @Test public void productionRootReaderCanCheckConfiguredFiles() throws Exception {
        android.content.Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        android.content.SharedPreferences prefs = context.getSharedPreferences("settings",0);
        String path = prefs.getString("path", "");
        if (!Python.isStarted()) Python.start(new AndroidPlatform(context));
        NativeBridge bridge = new NativeBridge(true, message -> {});
        String value = Python.getInstance().getModule("mobile_bridge").callAttr("run",bridge,path,"文件访问自检","ordinary",false,true,
            prefs.getString("rulesBase", "")).toString();
        JSONObject result = new JSONObject(value);
        assertTrue(value,result.getBoolean("ok"));
        assertTrue(result.getBoolean("checked"));
        Bundle message = new Bundle(); message.putString("stream", "\nProduction Root reader + embedded Python: all configured local files readable; no downloads.\n");
        InstrumentationRegistry.getInstrumentation().sendStatus(0,message);
    }
    @Test public void compareMountNamespaces() throws Exception {
        String command = "id; for p in /data/user/0/io.nekohasekai.sfa/files/configs/1.json /storage/emulated/0/Android/data/io.nekohasekai.sfa/files/RuleProviders/emby.json; do /system/bin/ls -ld \"$p\"; done";
        for (boolean master : new boolean[]{false,true}) {
            Process process = new ProcessBuilder(master ? new String[]{"su","-M","-c",command} : new String[]{"su","-c",command}).redirectErrorStream(true).start();
            if (!process.waitFor(20,TimeUnit.SECONDS)) { process.destroyForcibly(); throw new IllegalStateException("Root probe timed out"); }
            String result = new String(SafeFiles.readLimited(process.getInputStream()), StandardCharsets.UTF_8);
            Bundle message = new Bundle(); message.putString("stream", "\nmaster="+master+" exit="+process.exitValue()+"\n"+result);
            InstrumentationRegistry.getInstrumentation().sendStatus(0,message);
        }
    }
}
