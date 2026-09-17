-- Execute no SQL Editor do banco atual. Não apaga nem altera os setores existentes.
INSERT INTO public.setor (nome)
VALUES ('Padaria'), ('Açougue'), ('Mercearia'), ('Frios')
ON CONFLICT (nome) DO NOTHING;
