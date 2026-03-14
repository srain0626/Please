import json
import tempfile
import unittest

from agent.distribution import BlogChannelAdapterStub, MarketplaceChannelAdapterStub, OutreachChannelAdapterStub
from agent.persistence import SQLiteStore
from dashboard import render_dashboard


class DistributionLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db')
        self.store = SQLiteStore(self.tmp.name)
        self.mechanism_id = self.store.create_income_mechanism(
            mechanism_type='blogging',
            title='Blog Growth',
            description='blog distribution',
            expected_revenue=200,
            expected_cost=40,
            expected_token_cost=10,
            automation_potential=0.7,
            repeatability_score=0.6,
            maintenance_cost=15,
            current_stage='mvp',
            status='testing',
            confidence_score=0.5,
            time_to_payout=0.5,
        )
        self.blueprint_id = self.store.create_process_blueprint(
            mechanism_id=self.mechanism_id,
            task_type='blog_post_drafting',
            title='draft',
            description='d',
            inputs_schema='{}',
            output_schema='{}',
            steps_json='[]',
            can_be_templated=True,
            can_be_ruled=True,
            can_be_coded=False,
            automation_status='ready',
            estimated_token_cost=3.0,
            estimated_run_cost=0.2,
        )
        self.target_id = self.store.create_distribution_target(
            mechanism_id=self.mechanism_id,
            blueprint_id=self.blueprint_id,
            target_type='blog_post',
            title='Post 1',
            summary='s',
            payload_json=json.dumps({'body': 'hello'}),
            status='ready',
        )
        self.blog_channel = self.store.create_distribution_channel(
            channel_type='blog',
            name='local_blog_stub',
            description='local',
            config_json='{}',
            is_active=True,
        )
        self.email_channel = self.store.create_distribution_channel(
            channel_type='email',
            name='email_stub',
            description='email',
            config_json='{}',
            is_active=True,
        )
        self.market_channel = self.store.create_distribution_channel(
            channel_type='marketplace',
            name='market_stub',
            description='market',
            config_json='{}',
            is_active=True,
        )

    def tearDown(self) -> None:
        self.tmp.close()

    def test_target_and_channel_registry(self) -> None:
        self.assertTrue(self.store.list_distribution_targets(limit=10))
        channels = self.store.list_distribution_channels(limit=10)
        self.assertGreaterEqual(len(channels), 3)

    def test_distribution_run_and_stub_adapters(self) -> None:
        blog = BlogChannelAdapterStub(self.store).submit(
            target_id=self.target_id,
            channel_id=self.blog_channel,
            mechanism_id=self.mechanism_id,
            execution_mode='prompt_template',
        )
        self.assertEqual(blog.status, 'delivered')

        outreach = OutreachChannelAdapterStub(self.store).submit(
            target_id=self.target_id,
            channel_id=self.email_channel,
            mechanism_id=self.mechanism_id,
            execution_mode='rule_based',
        )
        self.assertIn(outreach.status, {'responded', 'failed'})

        market = MarketplaceChannelAdapterStub(self.store).submit(
            target_id=self.target_id,
            channel_id=self.market_channel,
            mechanism_id=self.mechanism_id,
            execution_mode='code_based',
        )
        self.assertIn(market.status, {'converted', 'failed'})

        runs = self.store.list_distribution_runs(limit=20)
        self.assertGreaterEqual(len(runs), 3)
        statuses = {r[5] for r in runs}
        self.assertTrue({'delivered'} & statuses)

    def test_conversion_event_and_feedback_updates_mechanism(self) -> None:
        before = self.store.list_income_mechanisms(limit=1)[0]
        run_id = self.store.create_distribution_run(
            target_id=self.target_id,
            channel_id=self.blog_channel,
            mechanism_id=self.mechanism_id,
            execution_mode='rule_based',
            status='submitted',
            external_ref='x',
            notes='n',
        )
        self.store.record_conversion_event(
            run_id=run_id,
            target_id=self.target_id,
            mechanism_id=self.mechanism_id,
            event_type='sale',
            value_estimate=100.0,
            metadata_json='{}',
        )
        self.store.apply_feedback_event('sale', self.mechanism_id)
        after = self.store.list_income_mechanisms(limit=1)[0]
        self.assertGreater(float(after[12]), float(before[12]))

    def test_dashboard_render_distribution_sections(self) -> None:
        html = render_dashboard(self.store)
        self.assertIn('Distribution Targets', html)
        self.assertIn('Distribution Channels', html)
        self.assertIn('Conversion Events', html)


if __name__ == '__main__':
    unittest.main()
