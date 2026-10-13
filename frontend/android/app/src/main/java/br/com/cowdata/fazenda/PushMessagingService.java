package br.com.cowdata.fazenda;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.core.app.NotificationCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class PushMessagingService extends FirebaseMessagingService {

    private static final String TAG = "PushMessagingService";
    private static final String CHANNEL_ID = "cowdata_notificacoes";
    private static final String CHANNEL_NAME = "Notificações CowData";
    private static final String PREF_NAME = "cowdata_push";
    private static final String PREF_USER_ID = "user_id";
    private static final String PREF_FCM_TOKEN = "fcm_token";
    private static final String PREF_BASE_URL = "base_url";
    
    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    @Override
    public void onMessageReceived(@NonNull RemoteMessage remoteMessage) {
        super.onMessageReceived(remoteMessage);
        Log.d(TAG, "Push recebido: " + remoteMessage.getFrom());
        
        // Extrai dados da mensagem
        String title = "";
        String body = "";
        String url = "/";
        String fcmMessageId = remoteMessage.getMessageId();
        int count = 0;
        
        if (remoteMessage.getNotification() != null) {
            title = remoteMessage.getNotification().getTitle() != null ? remoteMessage.getNotification().getTitle() : "";
            body = remoteMessage.getNotification().getBody() != null ? remoteMessage.getNotification().getBody() : "";
        }
        
        // Dados customizados (payload "data")
        if (remoteMessage.getData() != null) {
            if (remoteMessage.getData().containsKey("url")) {
                url = remoteMessage.getData().get("url");
            }
            if (remoteMessage.getData().containsKey("count")) {
                try {
                    count = Integer.parseInt(remoteMessage.getData().get("count"));
                } catch (NumberFormatException e) {
                    // ignora
                }
            }
        }
        
        // Determina estado do app
        String estadoApp = isAppInForeground() ? "primeiro_plano" : "segundo_plano";
        
        // Mostra a notificação
        mostrarNotificacao(title, body, url, count);
        
        // Envia ack para o backend
        enviarAck(fcmMessageId, estadoApp);
    }
    
    @Override
    public void onNewToken(@NonNull String token) {
        super.onNewToken(token);
        Log.d(TAG, "Novo token FCM: " + token);
        
        // Salva o token e notifica o app (quando abrir) para registrar no backend
        SharedPreferences prefs = getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
        prefs.edit().putString(PREF_FCM_TOKEN, token).apply();
    }
    
    private boolean isAppInForeground() {
        // Verifica se o app está em primeiro plano via ActivityLifecycleCallbacks
        // Por simplicidade, usamos SharedPreferences que o app atualiza
        SharedPreferences prefs = getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
        return prefs.getBoolean("app_em_primeiro_plano", false);
    }
    
    private void mostrarNotificacao(String title, String body, String url, int count) {
        createNotificationChannel();
        
        // Intent para abrir o app ao clicar na notificação
        Intent intent = new Intent(this, MainActivity.class);
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        // Passa a URL via extras para o app Web saber onde navegar
        intent.putExtra("push_url", url);
        
        PendingIntent pendingIntent = PendingIntent.getActivity(
            this, 0, intent, 
            PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT
        );
        
        // Ícone customizado
        int iconRes = getResources().getIdentifier("ic_notification_cowdata", "drawable", getPackageName());
        if (iconRes == 0) {
            iconRes = R.mipmap.ic_launcher; // fallback
        }
        
        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(iconRes)
            .setContentTitle(title)
            .setContentText(body)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pendingIntent)
            .setChannelId(CHANNEL_ID);
        
        if (count > 0) {
            builder.setNumber(count);
        }
        
        NotificationManager manager = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        int notificationId = (int) System.currentTimeMillis();
        manager.notify(notificationId, builder.build());
    }
    
    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_HIGH
            );
            channel.setDescription("Notificações de alertas do CowData (Agenda, Pendências, Comunicados)");
            channel.enableLights(true);
            channel.enableVibration(true);
            channel.setLockscreenVisibility(android.app.Notification.VISIBILITY_PUBLIC);
            
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }
    
    private void enviarAck(String fcmMessageId, String estadoApp) {
        SharedPreferences prefs = getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
        int userId = prefs.getInt(PREF_USER_ID, -1);
        String fcmToken = prefs.getString(PREF_FCM_TOKEN, "");
        String baseUrl = prefs.getString(PREF_BASE_URL, "");
        
        if (userId <= 0 || baseUrl.isEmpty()) {
            Log.w(TAG, "Não pode enviar ack: userId=" + userId + ", baseUrl=" + baseUrl);
            return;
        }
        
        String ackUrl = baseUrl + "/push/ack";
        
        executor.execute(() -> {
            try {
                JSONObject json = new JSONObject();
                if (fcmMessageId != null && !fcmMessageId.isEmpty()) {
                    json.put("fcm_message_id", fcmMessageId);
                }
                json.put("token_fcm", fcmToken);
                json.put("estado_app", estadoApp);
                
                java.net.HttpURLConnection conn = (java.net.HttpURLConnection) new java.net.URL(ackUrl).openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setRequestProperty("Authorization", "Bearer " + prefs.getString("auth_token", ""));
                conn.setDoOutput(true);
                conn.setConnectTimeout(10000);
                conn.setReadTimeout(10000);
                
                try (java.io.OutputStream os = conn.getOutputStream()) {
                    os.write(json.toString().getBytes("UTF-8"));
                }
                
                int responseCode = conn.getResponseCode();
                if (responseCode >= 200 && responseCode < 300) {
                    Log.d(TAG, "ACK enviado com sucesso: " + responseCode);
                } else {
                    Log.w(TAG, "Falha ao enviar ACK: " + responseCode);
                    try (java.io.BufferedReader br = new java.io.BufferedReader(new java.io.InputStreamReader(conn.getErrorStream()))) {
                        StringBuilder sb = new StringBuilder();
                        String line;
                        while ((line = br.readLine()) != null) sb.append(line);
                        Log.w(TAG, "Resposta erro: " + sb.toString());
                    }
                }
            } catch (IOException | JSONException e) {
                Log.e(TAG, "Erro ao enviar ACK", e);
            }
        });
    }
    
    // Métodos estáticos para o app (Capacitor) chamar
    
    public static void setUserId(Context context, int userId) {
        SharedPreferences prefs = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
        prefs.edit().putInt(PREF_USER_ID, userId).apply();
    }
    
    public static void setAuthToken(Context context, String token) {
        SharedPreferences prefs = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
        prefs.edit().putString("auth_token", token).apply();
    }
    
    public static void setBaseUrl(Context context, String baseUrl) {
        SharedPreferences prefs = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
        prefs.edit().putString(PREF_BASE_URL, baseUrl).apply();
    }
    
    public static void setAppForeground(Context context, boolean foreground) {
        SharedPreferences prefs = context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE);
        prefs.edit().putBoolean("app_em_primeiro_plano", foreground).apply();
    }
    
    public static String getPendingPushUrl(Context context) {
        // Não usado aqui, mas disponível se precisar
        return null;
    }
}