import 'package:flutter/material.dart';

import 'api.dart';
import 'format.dart';
import 'models.dart';
import 'share_form_screen.dart';
import 'theme.dart';
import 'widgets.dart';

typedef SharingData = ({
  List<Doctor> doctors,
  List<DiaryShare> shares,
  List<DiaryRead> reads,
  SharingContext consent,
});

class SharingScreen extends StatefulWidget {
  const SharingScreen({super.key, required this.api});
  final ApiClient api;

  @override
  State<SharingScreen> createState() => _SharingScreenState();
}

class _SharingScreenState extends State<SharingScreen> {
  late Future<SharingData> _data = _load();
  bool _revoking = false;
  String? _success;

  Future<SharingData> _load() async => (
    doctors: await widget.api.listDoctors(),
    shares: await widget.api.listShares(),
    reads: await widget.api.listReads(),
    consent: await widget.api.sharingContext(),
  );

  void _reload() {
    setState(() {
      _data = _load();
    });
  }

  Future<void> _create(SharingData data) async {
    final saved = await Navigator.of(context).push<DiaryShare>(
      MaterialPageRoute(
        builder: (_) =>
            ShareFormScreen(api: widget.api, doctors: data.doctors, consent: data.consent),
      ),
    );
    if (saved != null && mounted) {
      _success =
          'Your diary is now shared with ${_doctorName(data.doctors, saved.doctorId)}. '
          '${formatCalendarDate(DateTime.parse(saved.from))} to ${formatCalendarDate(DateTime.parse(saved.to))}. '
          '${saved.includeNotes ? 'Notes are included.' : 'Your notes stay private under this choice.'}';
      _reload();
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Your diary is shared.')));
    }
  }

  Future<void> _revoke(DiaryShare share) async {
    setState(() => _revoking = true);
    try {
      await widget.api.revokeShare(share.id);
      if (!mounted) return;
      _reload();
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Sharing stopped for these dates.')));
    } on Exception {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text("Couldn't stop sharing. Try again.")));
      }
    } finally {
      if (mounted) setState(() => _revoking = false);
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<SharingData>(
    future: _data,
    builder: (context, snapshot) {
      final data = snapshot.data;
      final ready =
          snapshot.connectionState == ConnectionState.done && !snapshot.hasError && data != null;
      final text = Theme.of(context).textTheme;
      return Scaffold(
        appBar: AppBar(
          title: const Text('Diary sharing'),
          actions: [
            IconButton(
              onPressed: _reload,
              tooltip: 'Refresh diary sharing',
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        bottomNavigationBar: ready
            ? SafeArea(
                child: ContentColumn(
                  child: Padding(
                    padding: const EdgeInsets.all(Space.m),
                    child: FilledButton.icon(
                      style: FilledButton.styleFrom(visualDensity: VisualDensity.standard),
                      onPressed: data.doctors.isEmpty || _revoking ? null : () => _create(data),
                      icon: const Icon(Icons.share_outlined),
                      label: const Text('Share diary with a doctor'),
                    ),
                  ),
                ),
              )
            : null,
        body: ListView(
          padding: const EdgeInsets.fromLTRB(Space.m, Space.m, Space.m, 112),
          children: [
            ContentColumn(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('Share your diary', style: text.headlineMedium),
                  const SizedBox(height: Space.s),
                  Text(
                    'Share a date range with your doctor. You choose whether to include notes, and you can stop sharing at any time.',
                    style: text.bodyLarge,
                  ),
                  const SizedBox(height: Space.l),
                  if (snapshot.hasError) ...[
                    const Text("Couldn't load diary sharing. Try again."),
                    TextButton(onPressed: _reload, child: const Text('Try again')),
                  ] else if (!ready)
                    const Center(child: CircularProgressIndicator())
                  else ...[
                    if (_success != null)
                      SharingCard(child: Semantics(liveRegion: true, child: Text(_success!))),
                    if (data.doctors.isEmpty)
                      const Text('No doctors are available. Try again later.'),
                    for (final past in [false, true]) ...[
                      if (!past || data.shares.any((share) => share.revoked))
                        Text(past ? 'Past sharing' : 'Currently sharing', style: text.titleMedium),
                      if (!past && !data.shares.any((share) => !share.revoked))
                        const SharingCard(child: Text('You are not sharing your diary yet.')),
                      for (final share in data.shares.where((share) => share.revoked == past))
                        SharingCard(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                _doctorName(data.doctors, share.doctorId),
                                style: text.titleMedium,
                              ),
                              const SizedBox(height: Space.s),
                              Text(
                                '${formatCalendarDate(DateTime.parse(share.from))} to ${formatCalendarDate(DateTime.parse(share.to))}',
                              ),
                              const Text('Both dates included'),
                              Text(
                                share.includeNotes
                                    ? 'Mood, symptoms and notes'
                                    : 'Mood and symptoms · Notes not included here',
                              ),
                              const SizedBox(height: Space.s),
                              Text(
                                share.revoked ? 'Sharing stopped' : 'Sharing on',
                                style: text.labelLarge,
                              ),
                              if (!share.revoked)
                                OutlinedButton(
                                  style: OutlinedButton.styleFrom(
                                    minimumSize: const Size.fromHeight(48),
                                    visualDensity: VisualDensity.standard,
                                    shape: const RoundedRectangleBorder(
                                      borderRadius: Radii.control,
                                    ),
                                  ),
                                  onPressed: _revoking ? null : () => _revoke(share),
                                  child: const Text('Stop sharing'),
                                ),
                            ],
                          ),
                        ),
                    ],
                    const SizedBox(height: Space.s),
                    Text(
                      'Stopping sharing on one card only stops that date range. If you shared other dates with the same doctor, check those cards too.',
                      style: text.bodyMedium,
                    ),
                    const SizedBox(height: Space.xl),
                    Text('Who opened your diary', style: text.titleMedium),
                    const SizedBox(height: Space.s),
                    Text(
                      'See when your doctor opened your diary. Times use your device timezone.',
                      style: text.bodyMedium,
                    ),
                    if (data.reads.isEmpty)
                      const SharingCard(child: Text('No doctor has opened your shared diary yet.')),
                    for (final read in data.reads)
                      SharingCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(read.doctorName, style: text.titleMedium),
                            Text(_readTime(read.accessedAt)),
                            Text(
                              '${read.entryIds.length} ${read.entryIds.length == 1 ? 'entry' : 'entries'} available to read',
                            ),
                          ],
                        ),
                      ),
                  ],
                ],
              ),
            ),
          ],
        ),
      );
    },
  );
}

String _doctorName(List<Doctor> doctors, int id) {
  for (final doctor in doctors) {
    if (doctor.id == id) return doctor.name;
  }
  return 'Your doctor';
}

String _readTime(DateTime value) {
  final local = value.toLocal();
  return '${formatCalendarDate(local)} at ${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
}

class SharingCard extends StatelessWidget {
  const SharingCard({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    margin: const EdgeInsets.only(bottom: Space.s, top: Space.s),
    padding: const EdgeInsets.all(Space.m),
    decoration: BoxDecoration(
      color: AppColors.surface,
      borderRadius: Radii.card,
      border: Border.all(color: AppColors.line),
    ),
    child: child,
  );
}
