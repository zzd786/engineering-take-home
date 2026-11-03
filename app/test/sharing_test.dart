import 'dart:convert';

import 'package:diary_app/api.dart';
import 'package:diary_app/main.dart';
import 'package:diary_app/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const contextData = {
  'timezone': 'Europe/Berlin',
  'today': '2026-10-08',
  'consent_version': 'diary-sharing-v2',
  'consent_template':
      'I agree to share my mood and symptoms with {doctor}. The dates are {from_date} through {to_date}, including both days, in {timezone}. {notes} I can stop sharing at any time. I can see which doctor opened my diary and when.',
};

class SharingServer {
  final requests = <http.Request>[];
  final shares = <Map<String, dynamic>>[];
  bool failLoad = false;
  bool failSave = false;
  bool failRevoke = false;
  bool history = false;
  bool failPreview = false;
  int entryCount = 12;
  int overlaps = 0;
  bool overlapNotes = false;

  late final api = ApiClient(
    client: MockClient((request) async {
      requests.add(request);
      final path = request.url.path;
      if (path.endsWith('/entries')) return http.Response('[]', 200);
      if (failLoad) return http.Response('{}', 503);
      if (path.endsWith('/clinicians')) {
        return http.Response(
          jsonEncode([
            {'id': 1, 'name': 'Dr. Example', 'practice': 'Example practice'},
          ]),
          200,
        );
      }
      if (path.endsWith('/sharing-preview')) {
        return http.Response(
          jsonEncode({
            'entry_count': entryCount,
            'note_entry_count': 4,
            'overlap_count': overlaps,
            'overlap_includes_notes': overlapNotes,
          }),
          failPreview ? 503 : 200,
        );
      }
      if (path.endsWith('/sharing-context')) return http.Response(jsonEncode(contextData), 200);
      if (path.endsWith('/access-log')) {
        return http.Response(
          jsonEncode(
            history
                ? [
                    {
                      'clinician_id': 1,
                      'clinician_name': 'Dr. Example',
                      'accessed_at': '2026-10-08T10:03:00Z',
                      'entry_ids': [3],
                    },
                  ]
                : [],
          ),
          200,
        );
      }
      if (path.endsWith('/revoke')) {
        if (failRevoke) return http.Response('{}', 503);
        shares.first['revoked_at'] = '2026-10-08T11:00:00Z';
        return http.Response(jsonEncode(shares.first), 200);
      }
      if (path.endsWith('/shares') && request.method == 'POST') {
        if (failSave) return http.Response('{}', 503);
        final share = {
          ...jsonDecode(request.body) as Map<String, dynamic>,
          'id': 1,
          'created_at': '2026-10-08T09:00:00Z',
          'revoked_at': null,
        };
        shares.add(share);
        return http.Response(jsonEncode(share), 201);
      }
      return http.Response(jsonEncode(shares), 200);
    }),
  );
}

Future<void> openSharing(WidgetTester tester, SharingServer server) async {
  await tester.pumpWidget(DiaryApp(api: server.api));
  await tester.pumpAndSettle();
  await tester.tap(find.widgetWithText(OutlinedButton, 'Share diary'));
  await tester.pumpAndSettle();
}

Future<void> openForm(WidgetTester tester) async {
  await tester.tap(find.text('Share diary with a doctor'));
  await tester.pumpAndSettle();
  await tester.tap(find.byType(DropdownButtonFormField<int>));
  await tester.pumpAndSettle();
  await tester.tap(find.text('Dr. Example').last);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shortcuts use saved timezone day and preview counts before saving', (tester) async {
    final server = SharingServer()
      ..overlaps = 1
      ..overlapNotes = true;
    await openSharing(tester, server);
    await openForm(tester);
    await tester.tap(find.text('Today'));
    await tester.pumpAndSettle();
    expect(jsonDecode(server.requests.last.body)['from_date'], '2026-10-08');
    await tester.tap(find.text('Last 30 days'));
    await tester.pumpAndSettle();
    expect(jsonDecode(server.requests.last.body)['from_date'], '2026-09-09');
    await tester.tap(find.text('Review sharing'));
    await tester.pumpAndSettle();
    expect(find.text('12 diary entries'), findsOneWidget);
    expect(find.textContaining('Leaving notes off'), findsOneWidget);
  });

  testWidgets('empty preview explains future entries and failed preview blocks review', (
    tester,
  ) async {
    final server = SharingServer()..entryCount = 0;
    await openSharing(tester, server);
    await openForm(tester);
    await tester.tap(find.text('Review sharing'));
    await tester.pumpAndSettle();
    expect(find.textContaining('There are no diary entries'), findsOneWidget);
    await tester.ensureVisible(find.text('Change doctor, dates or notes'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Change doctor, dates or notes'));
    await tester.pumpAndSettle();
    server.failPreview = true;
    await tester.tap(find.text('Today'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review sharing'));
    await tester.pumpAndSettle();
    expect(find.text("Couldn't check this period. Try again."), findsWidgets);
    expect(find.text('Confirm sharing'), findsNothing);
  });

  test('consent bullets retain the exact resolved text for both notes choices', () {
    final context = SharingContext.fromJson(contextData);
    final doctor = Doctor.fromJson({'id': 1, 'name': 'Dr. Example', 'practice': 'Example'});
    for (final notes in [false, true]) {
      final from = DateTime(2026, 10, 1);
      final to = DateTime(2026, 10, 7);
      final points = context.points(doctor, from, to, notes);
      expect(points.length, 5);
      expect(points.join(' '), context.wording(doctor, from, to, notes));
    }
  });

  testWidgets('diary sharing is a full-width outlined action', (tester) async {
    await tester.pumpWidget(DiaryApp(api: SharingServer().api));
    await tester.pumpAndSettle();
    final button = find.widgetWithText(OutlinedButton, 'Share diary');
    expect(button, findsOneWidget);
    expect(tester.getSize(button).width, 560);
    expect(tester.getSize(button).height, greaterThanOrEqualTo(52));
  });

  testWidgets('consent is a readable list that preserves the server wording', (tester) async {
    await openSharing(tester, SharingServer());
    await openForm(tester);
    await tester.tap(find.text('Review sharing'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('consent-point-0')), findsOneWidget);
    expect(find.byKey(const ValueKey('consent-point-3')), findsOneWidget);
    expect(find.text('I agree to share my mood and symptoms with Dr. Example.'), findsOneWidget);
    expect(find.text('I can stop sharing at any time.'), findsOneWidget);
    expect(find.text('My notes stay private.'), findsOneWidget);
  });

  testWidgets('sharing form has labelled controls and accessible tap targets', (tester) async {
    final handle = tester.ensureSemantics();
    try {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      final server = SharingServer();
      await openSharing(tester, server);
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await openForm(tester);
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
      await expectLater(tester, meetsGuideline(textContrastGuideline));
    } finally {
      handle.dispose();
      await tester.binding.setSurfaceSize(null);
    }
  });

  testWidgets('notes stay private and no grant is sent before confirmation', (tester) async {
    final server = SharingServer();
    await openSharing(tester, server);
    expect(find.text('You are not sharing your diary yet.'), findsOneWidget);
    await openForm(tester);
    expect(tester.widget<SwitchListTile>(find.byType(SwitchListTile)).value, isFalse);
    await tester.tap(find.text('Review sharing'));
    await tester.pumpAndSettle();
    expect(find.textContaining('My notes stay private.'), findsOneWidget);
    expect(find.textContaining('Europe/Berlin'), findsWidgets);
    expect(
      server.requests.where((r) => r.method == 'POST' && r.url.path.endsWith('/shares')),
      isEmpty,
    );
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm sharing'));
    await tester.pumpAndSettle();
    final sent = server.requests.singleWhere(
      (r) => r.method == 'POST' && r.url.path.endsWith('/shares'),
    );
    final body = jsonDecode(sent.body);
    expect(body['clinician_id'], 1);
    expect(body['include_notes'], false);
    expect(body['from_date'], matches(r'^\d{4}-\d{2}-\d{2}$'));
    expect(body['to_date'], matches(r'^\d{4}-\d{2}-\d{2}$'));
    expect(find.text('Sharing on'), findsOneWidget);
    expect(find.text('Currently sharing'), findsOneWidget);
    expect(find.textContaining('Your diary is now shared with Dr. Example.'), findsOneWidget);
  });

  testWidgets('explicit notes choice is shown and save failure keeps form', (tester) async {
    final server = SharingServer()..failSave = true;
    await openSharing(tester, server);
    await openForm(tester);
    await tester.drag(find.byType(ListView).last, const Offset(0, -350));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byType(Switch));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(Switch));
    await tester.tap(find.text('Review sharing'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Notes are included.'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm sharing'));
    await tester.pumpAndSettle();
    expect(find.text("Couldn't share your diary. Try again."), findsOneWidget);
    expect(jsonDecode(server.requests.last.body)['include_notes'], true);
  });

  testWidgets('doctor and date order are checked before review', (tester) async {
    final server = SharingServer();
    await openSharing(tester, server);
    await tester.tap(find.text('Share diary with a doctor'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review sharing'));
    await tester.pumpAndSettle();
    expect(find.text('Choose your doctor first.'), findsOneWidget);
    await tester.tap(find.byType(DropdownButtonFormField<int>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Dr. Example').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.textContaining('From:'));
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('From:'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Switch to input'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '01/01/2030');
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review sharing'));
    await tester.pumpAndSettle();
    await tester.drag(find.byType(ListView).last, const Offset(0, -400));
    await tester.pumpAndSettle();
    expect(find.text('The end date must be on or after the start date.'), findsOneWidget);
    expect(
      server.requests.where((r) => r.method == 'POST' && r.url.path.endsWith('/shares')),
      isEmpty,
    );
  });

  testWidgets('load failure offers retry', (tester) async {
    final server = SharingServer()..failLoad = true;
    await openSharing(tester, server);
    expect(find.text("Couldn't load diary sharing. Try again."), findsOneWidget);
    server.failLoad = false;
    await tester.tap(find.text('Try again'));
    await tester.pumpAndSettle();
    expect(find.text('You are not sharing your diary yet.'), findsOneWidget);
  });

  testWidgets('history is shown and revoke failure can be retried', (tester) async {
    final server = SharingServer()
      ..history = true
      ..failRevoke = true;
    server.shares.add({
      'id': 1,
      'clinician_id': 1,
      'from_date': '2026-10-01',
      'to_date': '2026-10-07',
      'include_notes': false,
      'created_at': '2026-10-08T09:00:00Z',
      'revoked_at': null,
    });
    await openSharing(tester, server);
    expect(find.text('Who opened your diary'), findsOneWidget);
    await tester.tap(find.text('Stop sharing'));
    await tester.pumpAndSettle();
    expect(find.text("Couldn't stop sharing. Try again."), findsOneWidget);
    server.failRevoke = false;
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Stop sharing'));
    await tester.tap(find.text('Stop sharing'));
    await tester.pumpAndSettle();
    expect(find.text('Sharing stopped'), findsOneWidget);
    expect(find.text('Past sharing'), findsOneWidget);
    expect(find.text('You are not sharing your diary yet.'), findsOneWidget);
    expect(find.text('Stop sharing'), findsNothing);
  });
}
