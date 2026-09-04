import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  const productionApplicationId = 'uk.co.politisltd.citizencentric.participant';

  test('Android production configuration is explicit and fail-closed', () {
    final gradle = File('android/app/build.gradle.kts').readAsStringSync();

    expect(gradle, contains('namespace = "$productionApplicationId"'));
    expect(gradle, contains('applicationId = "$productionApplicationId"'));
    expect(gradle, contains('compileSdk = 36'));
    expect(gradle, contains('targetSdk = 36'));
    expect(gradle, contains('minSdk = 24'));
    expect(gradle, contains('PCIP_ANDROID_KEYSTORE_PATH'));
    expect(gradle, contains('Production release signing is not configured'));
    expect(gradle, contains('signingConfigs.getByName("release")'));
    expect(gradle, isNot(contains('signingConfigs.getByName("debug")')));
    expect(gradle, contains('disable += "NotificationPermission"'));
  });

  test(
    'Android release manifest uses only participant-initiated permissions',
    () {
      final manifest = File('android/app/src/main/AndroidManifest.xml')
          .readAsStringSync();

      for (final permission in const [
        'android.permission.INTERNET',
        'android.permission.CAMERA',
        'android.permission.RECORD_AUDIO',
        'android.permission.ACCESS_COARSE_LOCATION',
        'android.permission.ACCESS_FINE_LOCATION',
      ]) {
        expect(manifest, contains(permission));
      }
      for (final permission in const [
        'android.permission.ACCESS_BACKGROUND_LOCATION',
        'android.permission.FOREGROUND_SERVICE_LOCATION',
        'android.permission.READ_MEDIA_IMAGES',
        'android.permission.READ_EXTERNAL_STORAGE',
        'android.permission.WRITE_EXTERNAL_STORAGE',
        'android.permission.MANAGE_EXTERNAL_STORAGE',
      ]) {
        expect(manifest, isNot(contains(permission)));
      }
      expect(manifest, contains('android:usesCleartextTraffic="false"'));
      expect(manifest, contains('android:enableOnBackInvokedCallback="true"'));
      expect(
        manifest,
        contains('android.hardware.camera" android:required="false"'),
      );
      expect(
        manifest,
        contains('android.hardware.microphone" android:required="false"'),
      );
      expect(
        manifest,
        contains('android.hardware.location" android:required="false"'),
      );
    },
  );

  test(
    'Android launch resources use the owned transparent Citizen Centric mark',
    () {
      expect(
        File('android/app/src/main/res/drawable/citizen_centric_mark.png')
            .existsSync(),
        isTrue,
      );
      expect(
        File('android/app/src/main/res/drawable/launch_background.xml')
            .readAsStringSync(),
        contains('@color/citizen_centric_launch_background'),
      );
      expect(
        File('android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml')
            .readAsStringSync(),
        contains('@drawable/citizen_centric_mark'),
      );
    },
  );

  test('location support is one-off foreground capture, not a stream', () {
    final app = File('lib/main.dart').readAsStringSync();

    expect(app, contains('Geolocator.getCurrentPosition'));
    expect(app, isNot(contains('Geolocator.getPositionStream')));
  });
}
