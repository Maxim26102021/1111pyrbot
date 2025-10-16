ALTER TABLE payments
ADD CONSTRAINT payments_provider_ext_id_key UNIQUE (provider, ext_id);
